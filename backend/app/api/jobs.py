"""Job routes. Thin: validate via schemas, call the services. Submitting a job only records it
and asks Temporal to start its workflow; the work itself never runs inside a request."""

import difflib
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.client import Client

from app.core.postgres_connection import postgres_connection
from app.db.models import Job
from app.repositories import domain_repo, job_repo, note_draft_repo, outline_draft_repo, step_run_repo
from app.schemas.jobs import (
    CLASSIFIER_CONFIDENCE_THRESHOLD,
    CreateJobRequest,
    DraftsResponse,
    DraftView,
    JobDetail,
    JobListResponse,
    JobOut,
    AttachmentView,
    LinkAdditionView,
    OutlineView,
    PlacementOptions,
    StepRunOut,
)
from app.schemas.outline import validate_outline
from app.services import commit_service, draft_service, job_service, placement_service
from app.services.job_service import InvalidJobInputError, JobStateError
from app.vault.paths import VaultPathError, resolve_in_vault
from app.workflows.models import DraftDecision, OutlineDecision

router = APIRouter()


def get_temporal(request: Request) -> Client:
    return request.app.state.temporal_client


def _title(job: Job) -> str:
    first = next((l.strip() for l in job.input_text.splitlines() if l.strip()), "")
    return first if len(first) <= 80 else first[:77] + "..."


def _out(job: Job) -> JobOut:
    return JobOut(
        id=job.id, title=_title(job), input_kind=job.input_kind, domain_choice=job.domain_choice,
        resolved_domains=job.resolved_domains or [], status=job.status, current_step=job.current_step,
        awaiting_owner=job.awaiting_owner, error=job.error, total_cost_usd=float(job.total_cost_usd or 0),
        created_at=job.created_at, updated_at=job.updated_at,
    )


@router.post("/jobs", response_model=JobOut, status_code=201)
async def create_job(
    body: CreateJobRequest, session: AsyncSession = Depends(postgres_connection.get_session), client: Client = Depends(get_temporal)
) -> JobOut:
    job = await job_service.start_job(session, client, input_kind=body.input_kind, text=body.text, domain_choice=body.domain_choice)
    return _out(job)


@router.get("/jobs", response_model=JobListResponse)
async def list_jobs(status: str | None = None, session: AsyncSession = Depends(postgres_connection.get_session)) -> JobListResponse:
    jobs = await job_repo.list_jobs(session, status.split(",") if status else None)
    return JobListResponse(jobs=[_out(j) for j in jobs])


@router.get("/jobs/{job_id}", response_model=JobDetail)
async def get_job(job_id: str, session: AsyncSession = Depends(postgres_connection.get_session)) -> JobDetail:
    job = await job_repo.get_job(session, job_id)
    steps = [
        StepRunOut(
            step=r.step, agent_role=r.agent_role, attempt=r.attempt, status=r.status, cost_usd=float(r.cost_usd),
            started_at=r.started_at, finished_at=r.finished_at, error=r.error,
        )
        for r in await step_run_repo.list_for_job(session, job_id)
    ]
    return JobDetail(**_out(job).model_dump(), steps=steps)


@router.get("/jobs/{job_id}/outline", response_model=OutlineView)
async def get_outline(job_id: str, session: AsyncSession = Depends(postgres_connection.get_session)) -> OutlineView:
    job = await job_repo.get_job(session, job_id)
    outline = await outline_draft_repo.get(session, job_id)
    if outline is None:
        raise JobStateError("this job has no outline right now")
    confidence = job.classifier_confidence
    placement: dict[str, PlacementOptions] = {}
    for slug in job.resolved_domains or []:
        hubs, notes = await placement_service.load_options(session, (await domain_repo.get_by_slug(session, slug)).id)
        placement[slug] = PlacementOptions(hubs=hubs, notes=notes)
    return OutlineView(
        outline=outline, placement=placement, resolved_domains=job.resolved_domains or [], classifier_confidence=confidence,
        low_confidence=confidence is not None and confidence < CLASSIFIER_CONFIDENCE_THRESHOLD,
        error=job.error if job.status == "awaiting_owner" else None,
    )


@router.post("/jobs/{job_id}/outline-decision", status_code=202)
async def outline_decision(
    job_id: str, decision: OutlineDecision,
    session: AsyncSession = Depends(postgres_connection.get_session), client: Client = Depends(get_temporal),
) -> dict:
    if decision.kind == "approve":
        problems = validate_outline(decision.tree) or await placement_service.validate_placement(session, decision.tree)
        if problems:
            raise InvalidJobInputError("that outline cannot be approved: " + "; ".join(problems))
    await job_service.send_outline_decision(session, client, job_id, decision)
    return {"accepted": True}


def _diff(vault: str, draft) -> str | None:
    if draft.kind != "merge" or not draft.path:
        return None
    try:
        current = resolve_in_vault(Path(vault), *draft.path.split("/")).read_text(encoding="utf-8")
    except (VaultPathError, FileNotFoundError):
        return None
    return "".join(difflib.unified_diff(
        current.splitlines(keepends=True), draft.body_md.splitlines(keepends=True),
        fromfile="on disk now", tofile="draft", n=3,
    ))


@router.get("/jobs/{job_id}/drafts", response_model=DraftsResponse)
async def get_drafts(job_id: str, session: AsyncSession = Depends(postgres_connection.get_session)) -> DraftsResponse:
    ctx = await draft_service.load_context(session, job_id)
    slug_of = {d.id: s for s, d in ctx.domains.items()}
    drafts = await note_draft_repo.list_for_job(session, job_id)
    views = [
        DraftView(
            node_key=d.node_key, domain_slug=slug_of[d.domain_id], title=d.title, kind=d.kind, stage=d.stage,
            path=d.path, parents=d.parents or [], body_md=d.body_md, validator_flags=d.validator_flags or [],
            diff=_diff(ctx.domains[slug_of[d.domain_id]].vault_path, d),
        )
        for d in drafts
    ]
    additions = await commit_service.planned_link_additions(session, ctx, drafts)
    attachments = commit_service.planned_reparents(ctx, drafts)
    return DraftsResponse(
        attachments=[AttachmentView(note_title=a.note_title, hub_title=a.hub_title, domain_slug=a.domain_slug) for a in attachments],
        drafts=views,
        link_additions=[
            LinkAdditionView(note_title=a.note_title, domain_slug=a.domain_slug, section=a.section, entry_title=a.entry_title)
            for a in additions
        ],
    )


@router.post("/jobs/{job_id}/draft-decision", status_code=202)
async def draft_decision(
    job_id: str, decision: DraftDecision,
    session: AsyncSession = Depends(postgres_connection.get_session), client: Client = Depends(get_temporal),
) -> dict:
    await job_service.send_draft_decision(session, client, job_id, decision)
    return {"accepted": True}


@router.post("/jobs/{job_id}/cancel", status_code=202)
async def cancel(
    job_id: str, session: AsyncSession = Depends(postgres_connection.get_session), client: Client = Depends(get_temporal)
) -> dict:
    await job_service.cancel_job(session, client, job_id)
    return {"accepted": True}

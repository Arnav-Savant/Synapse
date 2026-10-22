"""Job-level helpers shared by the API and the workflow activities."""

import copy
import logging

from sqlalchemy.ext.asyncio import AsyncSession
from temporalio.api.enums.v1 import WorkflowExecutionStatus
from temporalio.client import Client
from temporalio.service import RPCError, RPCStatusCode

from app.db.models import Domain, Job
from app.repositories import domain_repo, job_repo, note_draft_repo, outline_draft_repo
from app.schemas.domains import DomainProfile
from app.schemas.jobs import MAX_INPUT_CHARS
from app.workflows.client import ensure_admission_started
from app.workflows.ingest_workflow import IngestTopicWorkflow
from app.workflows.models import ADMISSION_WORKFLOW_ID, TASK_QUEUE, DraftDecision, OutlineDecision

logger = logging.getLogger(__name__)


class InvalidJobInputError(ValueError):
    """The submitted input is empty or otherwise unusable."""


class InputTooLargeError(ValueError):
    """The submitted input is over the size limit; it is rejected, never silently truncated."""


class JobStateError(RuntimeError):
    """The job is not in a state where that action makes sense (for example approving an outline it is not waiting on)."""


class JobStartError(RuntimeError):
    """The job row was created but its workflow could not be started."""


def snapshot_profiles(domains: list[Domain]) -> dict[str, dict]:
    """A deep copy of every domain's name, purpose and profile, so later profile edits
    never change a job that is already running (spec §20.7). Keyed by domain slug."""
    return {
        d.slug: {"name": d.name, "purpose": d.purpose, "profile": copy.deepcopy(d.profile or {})}
        for d in domains
    }


def profiles_for_job(job: Job, slugs: list[str]) -> list[tuple[str, DomainProfile]]:
    """(domain name, profile) for each slug, from the job's snapshot."""
    snapshot = job.profile_snapshot or {}
    return [(snapshot[s]["name"], DomainProfile.model_validate(snapshot[s]["profile"])) for s in slugs if s in snapshot]


async def start_job(session: AsyncSession, client: Client, *, input_kind: str, text: str, domain_choice: str) -> Job:
    text = text.strip()
    if not text:
        raise InvalidJobInputError("the input is empty")
    if len(text) > MAX_INPUT_CHARS:
        raise InputTooLargeError(f"the input is {len(text):,} characters; the limit is {MAX_INPUT_CHARS:,}. Split it into smaller submissions.")
    domains = await domain_repo.list_domains(session)
    if not domains:
        raise InvalidJobInputError("there are no domains yet; create one in Settings first")
    if domain_choice != "auto" and domain_choice not in {d.slug for d in domains}:
        raise domain_repo.DomainNotFoundError(f"no domain with slug {domain_choice!r}")

    job = await job_repo.create_job(
        session, input_kind=input_kind, input_text=text, domain_choice=domain_choice, profile_snapshot=snapshot_profiles(domains)
    )
    try:
        await ensure_admission_started(client)
        await client.start_workflow(IngestTopicWorkflow.run, job.id, id=job.id, task_queue=TASK_QUEUE)
    except Exception as exc:
        logger.exception("job %s: could not start its workflow", job.id[:8])
        await finish_job_row(session, job.id, "failed", f"could not start the pipeline: {exc}")
        raise JobStartError("the pipeline could not be started; is Temporal running? (docker compose up -d)") from exc
    logger.info("job %s: workflow started", job.id[:8])
    return job


async def finish_job_row(session: AsyncSession, job_id: str, status: str, error: str | None = None) -> int:
    """Terminal transition for the job row. Drafts are scratch space and go with the job. Returns how many drafts were dropped."""
    await outline_draft_repo.delete_for_job(session, job_id)
    dropped = await note_draft_repo.delete_for_job(session, job_id)
    await job_repo.set_status(session, job_id, status=status, awaiting_owner=False, error=error)
    return dropped


def _require_waiting(job: Job, step: str, what: str) -> None:
    if job.status != "awaiting_owner" or job.current_step != step:
        raise JobStateError(f"the job is not waiting for {what} (status {job.status}, step {job.current_step})")


async def send_outline_decision(session: AsyncSession, client: Client, job_id: str, decision: OutlineDecision) -> None:
    job = await job_repo.get_job(session, job_id)
    _require_waiting(job, "outline_gate", "an outline decision")
    await client.get_workflow_handle(job_id).signal(IngestTopicWorkflow.outline_decision, decision)
    logger.info("job %s: owner sent outline decision %r (%d node(s))", job_id[:8], decision.kind, len(decision.tree.nodes))


async def send_draft_decision(session: AsyncSession, client: Client, job_id: str, decision: DraftDecision) -> None:
    job = await job_repo.get_job(session, job_id)
    _require_waiting(job, "draft_gate", "draft review")
    await client.get_workflow_handle(job_id).signal(IngestTopicWorkflow.draft_decision, decision)
    logger.info("job %s: owner sent draft decision %r", job_id[:8], decision.kind)


async def cancel_job(session: AsyncSession, client: Client, job_id: str) -> None:
    job = await job_repo.get_job(session, job_id)
    if job.status in job_repo.TERMINAL_STATUSES:
        raise JobStateError(f"the job already ended ({job.status})")
    try:
        await client.get_workflow_handle(job_id).signal(IngestTopicWorkflow.cancel)
        logger.info("job %s: cancel requested", job_id[:8])
    except RPCError as exc:
        if exc.status != RPCStatusCode.NOT_FOUND:
            raise
        # The workflow is gone (for example it was deleted); close the row ourselves.
        await finish_job_row(session, job_id, "cancelled")
        logger.warning("job %s: its workflow no longer exists; marked cancelled", job_id[:8])


async def reconcile_job_rows(session: AsyncSession, client: Client) -> int:
    """After a restart: jobs whose workflow still runs are left alone (they resume by themselves);
    jobs whose workflow is gone are marked failed and give back their pipeline slot."""
    lost = 0
    for job in await job_repo.list_jobs(session, ["queued", "running", "awaiting_owner"]):
        try:
            description = await client.get_workflow_handle(job.id).describe()
            alive = description.status == WorkflowExecutionStatus.WORKFLOW_EXECUTION_STATUS_RUNNING
        except RPCError as exc:
            if exc.status != RPCStatusCode.NOT_FOUND:
                logger.warning("job %s: could not check its workflow (%s); leaving the row as it is", job.id[:8], exc)
                continue
            alive = False
        if alive:
            logger.info("job %s still running at step %s", job.id[:8], job.current_step)
            continue
        await finish_job_row(session, job.id, "failed", "workflow lost: the pipeline for this job no longer exists. Submit it again.")
        await client.get_workflow_handle(ADMISSION_WORKFLOW_ID).signal("release", job.id)
        logger.warning("job %s marked failed: its workflow no longer exists", job.id[:8])
        lost += 1
    return lost

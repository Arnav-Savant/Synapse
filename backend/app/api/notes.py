"""Notes routes. Thin: validate via schemas, call the services."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.postgres_connection import postgres_connection
from app.engines.factory import build_engine
from app.repositories import domain_repo
from app.schemas.notes import (
    DeletePlan,
    DeleteRequest,
    DeleteResponse,
    DeleteSelector,
    NotesResponse,
    ReconcileOut,
    ReconcileResponse,
    TidyPlan,
    TidyRequest,
    TidyResult,
)
from app.services import link_tidy_service, note_service
from app.services.reconcile_service import reconcile_all

router = APIRouter()


@router.get("/notes", response_model=NotesResponse)
async def list_notes(
    domain: str, q: str | None = None, session: AsyncSession = Depends(postgres_connection.get_session)
) -> NotesResponse:
    return NotesResponse(notes=await note_service.list_notes(session, domain, q))


@router.get("/notes/tidy-preview", response_model=TidyPlan)
async def tidy_preview(domain: str, session: AsyncSession = Depends(postgres_connection.get_session)) -> TidyPlan:
    return await link_tidy_service.build_tidy_plan(session, domain)


@router.post("/notes/tidy-review", response_model=TidyPlan)
async def tidy_review(domain: str, session: AsyncSession = Depends(postgres_connection.get_session)) -> TidyPlan:
    return await link_tidy_service.review_tidy_plan(session, build_engine(), domain)


@router.post("/notes/tidy", response_model=TidyResult)
async def tidy_notes(request: TidyRequest, session: AsyncSession = Depends(postgres_connection.get_session)) -> TidyResult:
    return await link_tidy_service.apply_tidy(session, request.domain_slug, request.extra)


@router.post("/notes/delete-preview", response_model=DeletePlan)
async def delete_preview(selector: DeleteSelector, session: AsyncSession = Depends(postgres_connection.get_session)) -> DeletePlan:
    return await note_service.preview_delete(session, selector)


@router.post("/notes/delete", response_model=DeleteResponse)
async def delete_notes(request: DeleteRequest, session: AsyncSession = Depends(postgres_connection.get_session)) -> DeleteResponse:
    return await note_service.delete(session, request)


@router.post("/notes/reconcile", response_model=ReconcileResponse)
async def reconcile(session: AsyncSession = Depends(postgres_connection.get_session)) -> ReconcileResponse:
    reports = await reconcile_all(session)
    return ReconcileResponse(domains={slug: ReconcileOut(**vars(r)) for slug, r in reports.items()})

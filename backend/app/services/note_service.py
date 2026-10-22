"""Note listing and deletion for the Notes page."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import domain_repo, note_index_repo
from app.schemas.notes import DeleteRequest, DeleteResponse, DeleteSelector, NoteOut
from app.schemas.notes import DeletePlan
from app.services import note_delete_service

logger = logging.getLogger(__name__)


class ConfirmationRequiredError(RuntimeError):
    """The delete includes notes the owner edited in Obsidian and was not explicitly confirmed."""


async def list_notes(session: AsyncSession, slug: str, q: str | None) -> list[NoteOut]:
    domain = await domain_repo.get_by_slug(session, slug)
    notes = await note_index_repo.list_notes(session, domain.id, q)
    twins = await note_index_repo.list_by_topic_ids(session, {n.topic_id for n in notes if n.topic_id})
    slug_by_id = {d.id: d.slug for d in await domain_repo.list_domains(session)}
    return [
        NoteOut(
            synapse_id=n.synapse_id, title=n.title, path=n.path, summary=n.summary, domain_slug=slug,
            user_modified=n.user_modified, is_hub=n.is_hub, job_id=n.job_id,
            twin_domains=sorted({slug_by_id[t.domain_id] for t in twins if t.topic_id == n.topic_id and t.domain_id != domain.id}) if n.topic_id else [],
        )
        for n in notes
    ]


async def preview_delete(session: AsyncSession, selector: DeleteSelector) -> DeletePlan:
    domain = await domain_repo.get_by_slug(session, selector.domain)
    return await note_delete_service.build_delete_plan(
        session, domain, note_ids=selector.note_ids, topic_folder=selector.topic_folder,
        job_id=selector.job_id, twin_scope=selector.twin_scope,
    )


async def delete(session: AsyncSession, request: DeleteRequest) -> DeleteResponse:
    """Recomputes the plan from the selector instead of trusting a client-held one, so what is
    deleted is exactly what the files say now."""
    plan = await preview_delete(session, request)
    if plan.needs_extra_confirm and not request.confirm_modified:
        titles = ", ".join(repr(n.title) for n in plan.needs_extra_confirm)
        raise ConfirmationRequiredError(f"these notes were edited in Obsidian and need explicit confirmation: {titles}")
    await note_delete_service.apply_delete_plan(session, plan)
    return DeleteResponse(deleted=len(plan.delete_notes), links_stripped_in=len(plan.edits), children_reattached=len(plan.reparent))

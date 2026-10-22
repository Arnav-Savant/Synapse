"""Note draft repository: drafts live only in Postgres, are overwritten on regeneration
and deleted on approval or cancel. No history is kept."""

from datetime import datetime, timezone

from sqlalchemy import delete, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NoteDraft

_FIELDS = {
    "title", "parents", "body_md", "frontmatter", "kind", "path", "target_note_id",
    "base_hash", "validator_flags", "dossier", "stage",
}


class NoteDraftNotFoundError(LookupError):
    """No draft exists for that job, domain and node."""


async def upsert(session: AsyncSession, job_id: str, domain_id: str, node_key: str, **fields) -> NoteDraft:
    """Creates the draft, or overwrites the fields given on the existing one
    (unique per job, domain and node). Fields not given keep their value."""
    unknown = set(fields) - _FIELDS
    if unknown:
        raise TypeError(f"unknown note draft field(s): {sorted(unknown)}")

    existing = await _find(session, job_id, domain_id, node_key)
    if existing is not None:
        for name, value in fields.items():
            setattr(existing, name, value)
        await session.commit()
        return existing

    if "title" not in fields:
        raise TypeError("a new note draft needs a title")
    # Insert-or-update, so two concurrent activities creating the same draft cannot collide.
    stmt = insert(NoteDraft).values(job_id=job_id, domain_id=domain_id, node_key=node_key, **fields).on_conflict_do_update(
        constraint="uq_note_drafts_job_domain_node", set_={**fields, "updated_at": datetime.now(timezone.utc)}
    )
    await session.execute(stmt)
    await session.commit()
    return await get(session, job_id, domain_id, node_key)


async def _find(session: AsyncSession, job_id: str, domain_id: str, node_key: str) -> NoteDraft | None:
    result = await session.execute(
        select(NoteDraft).where(
            NoteDraft.job_id == job_id, NoteDraft.domain_id == domain_id, NoteDraft.node_key == node_key
        )
    )
    row = result.scalars().first()
    if row is not None:
        await session.refresh(row)  # the upsert bypassed the ORM, so any cached copy is stale
    return row


async def get(session: AsyncSession, job_id: str, domain_id: str, node_key: str) -> NoteDraft:
    row = await _find(session, job_id, domain_id, node_key)
    if row is None:
        raise NoteDraftNotFoundError(f"no draft for job {job_id[:8]}, node {node_key!r}")
    return row


async def list_for_job(session: AsyncSession, job_id: str) -> list[NoteDraft]:
    result = await session.execute(select(NoteDraft).where(NoteDraft.job_id == job_id).order_by(NoteDraft.node_key))
    rows = list(result.scalars().all())
    for row in rows:
        await session.refresh(row)
    return rows


async def delete_for_job(session: AsyncSession, job_id: str) -> int:
    result = await session.execute(delete(NoteDraft).where(NoteDraft.job_id == job_id))
    await session.commit()
    return result.rowcount or 0


async def delete_by_ids(session: AsyncSession, draft_ids: list[str]) -> None:
    if draft_ids:
        await session.execute(delete(NoteDraft).where(NoteDraft.id.in_(draft_ids)))
        await session.commit()

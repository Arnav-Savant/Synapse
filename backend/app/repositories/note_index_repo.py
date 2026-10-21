"""Note index repository: the derived, rebuildable Postgres copy of what is in
the vaults (`notes`, `note_links`).

Unlike the other repositories these functions only `flush`, never `commit`:
a commit or delete updates the index for many notes and their links as one
transaction, so the calling service owns the commit. `Note.path` is stored
relative to the domain's vault folder, with `/` separators.
"""

import logging
import re
from dataclasses import dataclass

from sqlalchemy import ARRAY, Text, bindparam, delete, func, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Note, NoteLink

logger = logging.getLogger(__name__)

_MAX_TS_TOKENS = 20


class NoteNotFoundError(LookupError):
    """No indexed note exists for the given synapse_id."""


@dataclass(frozen=True)
class Candidate:
    note: Note
    score: float


def _like_escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


async def upsert_note(
    session: AsyncSession,
    *,
    synapse_id: str,
    domain_id: str,
    title: str,
    path: str,
    aliases: list[str],
    summary: str,
    content_hash: str,
    topic_id: str | None = None,
    job_id: str | None = None,
    user_modified: bool = False,
) -> Note:
    note = await session.get(Note, synapse_id)
    if note is None:
        note = Note(synapse_id=synapse_id)
        session.add(note)
    note.domain_id = domain_id
    note.title = title
    note.path = path
    note.aliases = list(aliases)
    note.summary = summary
    note.content_hash = content_hash
    note.topic_id = topic_id
    note.job_id = job_id
    note.user_modified = user_modified
    await session.flush()
    return note


async def replace_links(
    session: AsyncSession, src_note_id: str, links: list[tuple[str | None, str, str]]
) -> None:
    """links: (dst_note_id or None when unresolved, dst_title, kind)."""
    await session.execute(delete(NoteLink).where(NoteLink.src_note_id == src_note_id))
    for dst_note_id, dst_title, kind in links:
        session.add(NoteLink(src_note_id=src_note_id, dst_note_id=dst_note_id, dst_title=dst_title, kind=kind))
    await session.flush()


async def get_note(session: AsyncSession, synapse_id: str) -> Note:
    note = await session.get(Note, synapse_id)
    if note is None:
        raise NoteNotFoundError(f"no indexed note with id {synapse_id!r}")
    return note


async def list_notes(session: AsyncSession, domain_id: str, q: str | None = None) -> list[Note]:
    stmt = select(Note).where(Note.domain_id == domain_id).order_by(func.lower(Note.title))
    if q and q.strip():
        stmt = stmt.where(
            or_(
                Note.title.ilike(f"%{_like_escape(q.strip())}%", escape="\\"),
                Note.tsv.op("@@")(func.plainto_tsquery("simple", q.strip())),
            )
        )
    result = await session.execute(stmt)
    return list(result.scalars().all())


async def find_by_title_key(session: AsyncSession, domain_id: str, title: str) -> Note | None:
    result = await session.execute(
        select(Note).where(Note.domain_id == domain_id, func.lower(Note.title) == title.lower())
    )
    return result.scalars().first()


async def list_notes_for_job(session: AsyncSession, job_id: str) -> list[Note]:
    result = await session.execute(select(Note).where(Note.job_id == job_id))
    return list(result.scalars().all())


async def list_notes_in_folder(session: AsyncSession, domain_id: str, folder: str) -> list[Note]:
    result = await session.execute(
        select(Note).where(Note.domain_id == domain_id, Note.path.like(f"{_like_escape(folder)}/%", escape="\\"))
    )
    return list(result.scalars().all())


async def list_by_topic_ids(session: AsyncSession, topic_ids: set[str]) -> list[Note]:
    if not topic_ids:
        return []
    result = await session.execute(select(Note).where(Note.topic_id.in_(topic_ids)))
    return list(result.scalars().all())


def _ts_query(*texts: str) -> str:
    tokens: list[str] = []
    for t in texts:
        for token in re.findall(r"\w+", t.lower()):
            if token not in tokens:
                tokens.append(token)
    return " | ".join(tokens[:_MAX_TS_TOKENS])


async def find_candidates(
    session: AsyncSession, domain_id: str, *, title: str, aliases: list[str], summary: str, limit: int = 8
) -> list[Candidate]:
    """Overlap candidates within one domain, never across domains. Ranked: an
    exact title/alias match first, then full-text rank, then trigram
    similarity of the titles."""
    terms = [t.lower() for t in [title, *aliases] if t.strip()]
    ts_query = _ts_query(title, *aliases, summary)
    stmt = text(
        """
        SELECT synapse_id, exact, rank, sim FROM (
            SELECT n.synapse_id,
                   (lower(n.title) = ANY(:terms)
                    OR EXISTS (SELECT 1 FROM unnest(n.aliases) a WHERE lower(a) = ANY(:terms))) AS exact,
                   CASE WHEN :ts_query = '' THEN 0
                        ELSE ts_rank(n.tsv, to_tsquery('simple', :ts_query)) END AS rank,
                   (SELECT coalesce(max(similarity(n.title, t)), 0) FROM unnest(:terms) AS t) AS sim,
                   (:ts_query <> '' AND n.tsv @@ to_tsquery('simple', :ts_query)) AS ts_hit
            FROM notes n
            WHERE n.domain_id = :domain_id
        ) scored
        WHERE exact OR ts_hit OR sim > 0.3
        ORDER BY exact DESC, rank DESC, sim DESC
        LIMIT :limit
        """
    ).bindparams(bindparam("terms", type_=ARRAY(Text)))
    rows = (
        await session.execute(stmt, {"terms": terms, "ts_query": ts_query, "domain_id": domain_id, "limit": limit})
    ).all()
    if not rows:
        return []
    by_id = {
        n.synapse_id: n
        for n in (await session.execute(select(Note).where(Note.synapse_id.in_([r.synapse_id for r in rows])))).scalars()
    }
    return [
        Candidate(note=by_id[r.synapse_id], score=2.0 if r.exact else float(r.rank) + float(r.sim))
        for r in rows
        if r.synapse_id in by_id
    ]


async def inbound_links(session: AsyncSession, note_id: str) -> list[Note]:
    """Notes whose indexed links point at this note (by id, or by its title when unresolved)."""
    note = await get_note(session, note_id)
    result = await session.execute(
        select(Note)
        .join(NoteLink, NoteLink.src_note_id == Note.synapse_id)
        .where(
            Note.domain_id == note.domain_id,
            Note.synapse_id != note.synapse_id,
            or_(NoteLink.dst_note_id == note.synapse_id, func.lower(NoteLink.dst_title) == note.title.lower()),
        )
        .distinct()
    )
    return list(result.scalars().all())


async def children_of(session: AsyncSession, note_id: str) -> list[Note]:
    """Notes that list this note as a parent."""
    note = await get_note(session, note_id)
    result = await session.execute(
        select(Note)
        .join(NoteLink, NoteLink.src_note_id == Note.synapse_id)
        .where(
            Note.domain_id == note.domain_id,
            NoteLink.kind == "parent",
            or_(NoteLink.dst_note_id == note.synapse_id, func.lower(NoteLink.dst_title) == note.title.lower()),
        )
        .distinct()
    )
    return list(result.scalars().all())


async def parent_titles(session: AsyncSession, note_id: str) -> list[str]:
    result = await session.execute(
        select(NoteLink.dst_title).where(NoteLink.src_note_id == note_id, NoteLink.kind == "parent")
    )
    return list(result.scalars().all())


async def delete_note(session: AsyncSession, synapse_id: str) -> None:
    """Removes the row; its outgoing links go with it, inbound links keep their title with no id."""
    await session.execute(delete(Note).where(Note.synapse_id == synapse_id))
    await session.flush()

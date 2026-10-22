"""Commit: the only place approved drafts become files in a vault (spec §8 step 12, §10, §20).

Nothing here trusts an agent. Every path is resolved inside the vault, titles are checked for
uniqueness, and a merge is written only if the file on disk is still the one the draft was based
on, so the owner's Obsidian edits are never overwritten. The commit is idempotent: a crash halfway is
repaired by running it again, because a file that already holds the draft's exact text is simply
indexed, not rewritten.
"""

import hashlib
import logging
from pathlib import Path

from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import NoteDraft
from app.repositories import note_draft_repo, note_index_repo
from app.services.draft_service import DraftContext, load_context
from app.services.note_link_index import reindex_note_links
from app.vault.assemble import insert_link_line
from app.vault.frontmatter import FrontmatterError, split_frontmatter
from app.vault.locks import vault_lock
from app.vault.paths import VaultPathError, resolve_in_vault
from app.vault.store import VaultWriteError, file_hash, write_note_atomic
from app.workflows.models import round_key

logger = logging.getLogger(__name__)


class CommitFailure(BaseModel):
    key: str  # `node_key|domain`
    reason: str


class CommitSummary(BaseModel):
    committed: list[str] = []
    stale: list[str] = []
    failed: list[CommitFailure] = []


class LinkAddition(BaseModel):
    """A line added to an EXISTING note when a draft is approved; listed at Gate 2 as `will add link in [[X]]`."""

    note_id: str
    note_title: str
    domain_slug: str
    section: str
    entry_title: str
    entry_note: str


def _sha(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def select_drafts(drafts: list[NoteDraft], slug_of: dict[str, str], node_keys: list[str] | None) -> list[NoteDraft]:
    """None selects all. An entry `node|domain` selects that one draft; a bare node key selects its drafts in every domain."""
    if node_keys is None:
        return list(drafts)
    wanted = set(node_keys)
    return [d for d in drafts if d.node_key in wanted or round_key(d.node_key, slug_of[d.domain_id]) in wanted]


async def planned_link_additions(session: AsyncSession, ctx: DraftContext, drafts: list[NoteDraft]) -> list[LinkAddition]:
    """Back-links an approved draft adds to the existing note it partially overlaps (`partial` verdict)."""
    slug_of = {d.id: s for s, d in ctx.domains.items()}
    additions: list[LinkAddition] = []
    for draft in drafts:
        slug = slug_of[draft.domain_id]
        node = ctx.nodes.get(draft.node_key)
        verdict = node.verdicts.get(slug) if node else None
        if draft.kind != "new" or verdict is None or verdict.kind != "partial" or not verdict.target_note_id:
            continue
        try:
            target = await note_index_repo.get_note(session, verdict.target_note_id)
        except note_index_repo.NoteNotFoundError:
            continue
        additions.append(LinkAddition(
            note_id=target.synapse_id, note_title=target.title, domain_slug=slug, section="Related",
            entry_title=draft.title, entry_note=verdict.reason or "overlapping topic",
        ))
    return additions


async def commit_drafts(session: AsyncSession, job_id: str, node_keys: list[str] | None) -> CommitSummary:
    ctx = await load_context(session, job_id)
    slug_of = {d.id: s for s, d in ctx.domains.items()}
    chosen = select_drafts(await note_draft_repo.list_for_job(session, job_id), slug_of, node_keys)
    summary = CommitSummary()
    committed_ids: list[str] = []

    for slug in sorted({slug_of[d.domain_id] for d in chosen}):
        domain = ctx.domains[slug]
        async with vault_lock(slug):
            written: list[tuple[NoteDraft, str]] = []
            for draft in [d for d in chosen if slug_of[d.domain_id] == slug]:
                outcome = await _commit_one(session, Path(domain.vault_path), domain.id, draft)
                key = round_key(draft.node_key, slug)
                if outcome == "committed":
                    written.append((draft, key))
                elif outcome == "stale":
                    summary.stale.append(key)
                    await note_draft_repo.upsert(session, job_id, domain.id, draft.node_key, stage="stale")
                else:
                    summary.failed.append(CommitFailure(key=key, reason=outcome))
                    flags = [f for f in draft.validator_flags if f.get("code") != "commit_failed"]
                    await note_draft_repo.upsert(
                        session, job_id, domain.id, draft.node_key,
                        validator_flags=flags + [{"code": "commit_failed", "message": outcome}],
                    )

            for addition in await planned_link_additions(session, ctx, [d for d, _ in written]):
                if addition.domain_slug == slug:
                    await _apply_link_addition(session, Path(domain.vault_path), addition)

            await session.flush()
            for draft, key in written:  # links resolve once every new note of this vault is in the index
                note = await note_index_repo.get_note(session, (draft.frontmatter or {}).get("synapse_id"))
                await reindex_note_links(session, note, draft.body_md)
                summary.committed.append(key)
                committed_ids.append(draft.id)
            await session.commit()

    await note_draft_repo.delete_by_ids(session, committed_ids)
    logger.info(
        "job %s commit: %d written, %d stale (to regenerate), %d refused",
        job_id[:8], len(summary.committed), len(summary.stale), len(summary.failed),
    )
    for failure in summary.failed:
        logger.warning("job %s: %s was not committed: %s", job_id[:8], failure.key, failure.reason)
    return summary


async def _commit_one(session: AsyncSession, vault: Path, domain_id: str, draft: NoteDraft) -> str:
    """Returns "committed", "stale", or the reason it was refused."""
    try:
        meta, _ = split_frontmatter(draft.body_md)
    except FrontmatterError as exc:
        return f"the draft's frontmatter is unreadable: {exc}"
    synapse_id = meta.get("synapse_id")
    if not synapse_id or not draft.path:
        return "the draft has no id or target path"
    try:
        path = resolve_in_vault(vault, *draft.path.split("/"))
    except VaultPathError as exc:
        return str(exc)

    text_hash = _sha(draft.body_md)
    already_written = path.is_file() and file_hash(path) == text_hash  # a crash-retry: only the index is missing

    if not already_written:
        if draft.kind == "merge":
            if not draft.target_note_id:
                return "a merge draft has no target note"
            if not path.is_file():
                return f"the note it was going to merge into ({draft.path}) no longer exists on disk"
            if file_hash(path) != draft.base_hash:
                return "stale"  # edited since the draft was made: never overwrite, regenerate from the current file
        else:
            existing = await note_index_repo.find_by_title_key(session, domain_id, draft.title)
            if existing is not None and existing.synapse_id != synapse_id:
                return f"a note titled {draft.title!r} already exists in this vault"
            if path.exists():
                return f"a file already exists at {draft.path} that is not tracked as this note"
        try:
            content_hash = write_note_atomic(path, draft.body_md)
        except VaultWriteError as exc:
            return str(exc)
    else:
        content_hash = text_hash

    await note_index_repo.upsert_note(
        session, synapse_id=synapse_id, domain_id=domain_id, title=draft.title, path=draft.path,
        aliases=[str(a) for a in (meta.get("aliases") or [])], summary=str(meta.get("summary") or ""),
        content_hash=content_hash, topic_id=meta.get("topic_id"), job_id=meta.get("job_id"),
        user_modified=False,  # this version began from the file on disk, so the owner's edits are in it
    )
    return "committed"


async def _apply_link_addition(session: AsyncSession, vault: Path, addition: LinkAddition) -> None:
    """A line-level insertion into an existing note; every other line stays byte-identical,
    and `user_modified` is left as it was (the owner's edits are still there)."""
    try:
        note = await note_index_repo.get_note(session, addition.note_id)
        path = resolve_in_vault(vault, *note.path.split("/"))
        text = path.read_text(encoding="utf-8")
    except (note_index_repo.NoteNotFoundError, VaultPathError, FileNotFoundError) as exc:
        logger.warning("could not add a link in %r (%s); skipping", addition.note_title, exc)
        return
    updated = insert_link_line(text, addition.section, (addition.entry_title, addition.entry_note))
    if updated == text:
        return
    note.content_hash = write_note_atomic(path, updated)
    await reindex_note_links(session, note, updated)
    logger.info("added a link to %r in %r (%s)", addition.entry_title, addition.note_title, addition.section)


async def discard_unselected(session: AsyncSession, job_id: str, node_keys: list[str] | None) -> int:
    """Approving a subset means the rest are not wanted: drop every draft that was not selected."""
    if node_keys is None:
        return 0
    ctx = await load_context(session, job_id)
    slug_of = {d.id: s for s, d in ctx.domains.items()}
    drafts = await note_draft_repo.list_for_job(session, job_id)
    keep = {d.id for d in select_drafts(drafts, slug_of, node_keys)}
    doomed = [d.id for d in drafts if d.id not in keep]
    await note_draft_repo.delete_by_ids(session, doomed)
    if doomed:
        logger.info("job %s: %d unselected draft(s) discarded", job_id[:8], len(doomed))
    return len(doomed)

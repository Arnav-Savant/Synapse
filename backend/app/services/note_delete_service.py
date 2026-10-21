"""Deterministic note deletion (spec §13): no LLM, preview first, no ghost links.

`build_delete_plan` has no side effects. It works from the files on disk,
not from the index, because the owner edits notes in Obsidian and the index
can lag behind. `apply_delete_plan` re-reads every file under the vault lock
and is idempotent, so a crash halfway is repaired by running it again.

Selection: `note_ids` and `topic_folder` act inside the given domain
(`twin_scope="all"` also takes each note's twins in other vaults);
`job_id` takes everything that job created, in every vault.
"""

import logging
from pathlib import Path
from typing import Literal

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Domain, Note
from app.repositories import domain_repo, note_index_repo
from app.schemas.notes import DeletePlan, FileEdit, NoteRef, ReparentChange
from app.services.note_link_index import parent_titles_from_text, reindex_note_links
from app.vault.assemble import drop_empty_sections, set_parents
from app.vault.locks import vault_lock
from app.vault.paths import resolve_in_vault
from app.vault.store import write_note_atomic
from app.vault.titles import title_key
from app.vault.wikilinks import find_wikilinks, remove_links_to

logger = logging.getLogger(__name__)


class DeleteSelectionError(ValueError):
    """The delete request selects nothing, or more than one way of selecting."""


def _note_path(vault_root: Path, note: Note) -> Path:
    return resolve_in_vault(vault_root, *note.path.split("/"))


def _read(vault_root: Path, note: Note) -> str | None:
    try:
        return _note_path(vault_root, note).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


def _rewrite(text: str, deleted_keys: set[str], new_parents: list[str] | None) -> str:
    """Re-attach first (rewrites `parents` and `Up:`), strip the remaining links, then drop sections left empty."""
    if new_parents is not None:
        text = set_parents(text, new_parents)
    return drop_empty_sections(remove_links_to(text, deleted_keys))


def _count_links(text: str, deleted_keys: set[str]) -> int:
    return sum(1 for l in find_wikilinks(text) if l.target and title_key(l.target) in deleted_keys)


def _ref(note: Note, slug: str) -> NoteRef:
    return NoteRef(
        synapse_id=note.synapse_id, title=note.title, path=note.path, domain_slug=slug, user_modified=note.user_modified
    )


async def _select(
    session: AsyncSession,
    domain: Domain,
    note_ids: list[str] | None,
    topic_folder: str | None,
    job_id: str | None,
    twin_scope: str,
) -> list[Note]:
    chosen = [x for x in (note_ids, topic_folder, job_id) if x]
    if len(chosen) != 1:
        raise DeleteSelectionError("choose exactly one of note_ids, topic_folder or job_id")

    if note_ids:
        notes = [await note_index_repo.get_note(session, nid) for nid in note_ids]
        if any(n.domain_id != domain.id for n in notes):
            raise DeleteSelectionError(f"some of those notes are not in domain {domain.slug!r}")
    elif topic_folder:
        resolve_in_vault(Path(domain.vault_path), topic_folder)  # rejects '..' and absolute paths
        notes = await note_index_repo.list_notes_in_folder(session, domain.id, topic_folder.strip("/"))
    else:
        notes = await note_index_repo.list_notes_for_job(session, job_id)

    if twin_scope == "all":
        notes += await note_index_repo.list_by_topic_ids(session, {n.topic_id for n in notes if n.topic_id})
    unique = {n.synapse_id: n for n in notes}
    if not unique:
        raise DeleteSelectionError("nothing matches that selection")
    return list(unique.values())


async def build_delete_plan(
    session: AsyncSession,
    domain: Domain,
    *,
    note_ids: list[str] | None = None,
    topic_folder: str | None = None,
    job_id: str | None = None,
    twin_scope: Literal["this", "all"] = "this",
) -> DeletePlan:
    doomed = await _select(session, domain, note_ids, topic_folder, job_id, twin_scope)
    domains: dict[str, Domain] = {domain.id: domain}
    for note in doomed:
        if note.domain_id not in domains:
            domains[note.domain_id] = await domain_repo.get_by_id(session, note.domain_id)

    plan = DeletePlan(delete_notes=[], edits=[], reparent=[], needs_extra_confirm=[])
    for dom in domains.values():
        in_domain = [n for n in doomed if n.domain_id == dom.id]
        refs = [_ref(n, dom.slug) for n in in_domain]
        plan.delete_notes += refs
        plan.needs_extra_confirm += [r for r in refs if r.user_modified]
        await _plan_domain(session, dom, in_domain, plan)

    logger.info(
        "delete preview: %d note(s) in %d vault(s), %d file(s) to strip links from, %d child(ren) to re-attach",
        len(plan.delete_notes), len(domains), len(plan.edits), len(plan.reparent),
    )
    return plan


async def _plan_domain(session: AsyncSession, dom: Domain, doomed: list[Note], plan: DeletePlan) -> None:
    vault = Path(dom.vault_path)
    doomed_ids = {n.synapse_id for n in doomed}
    deleted_keys = {title_key(n.title) for n in doomed}

    # What each doomed note's own parents are: the file is authoritative, the index the fallback.
    parents_of: dict[str, list[str]] = {}
    for note in doomed:
        text = _read(vault, note)
        parents_of[title_key(note.title)] = (
            parent_titles_from_text(text) if text is not None else await note_index_repo.parent_titles(session, note.synapse_id)
        )

    def surviving_parents(titles: list[str], seen: frozenset[str] = frozenset()) -> list[str]:
        """Parents to keep: a deleted parent is replaced by its own parents, transitively."""
        result: list[str] = []
        for title in titles:
            key = title_key(title)
            if key not in deleted_keys:
                candidates = [title]
            elif key in seen:
                candidates = []
            else:
                candidates = surviving_parents(parents_of.get(key, []), seen | {key})
            for candidate in candidates:
                if title_key(candidate) not in {title_key(r) for r in result}:
                    result.append(candidate)
        return result

    for note in await note_index_repo.list_notes(session, dom.id):
        if note.synapse_id in doomed_ids:
            continue
        text = _read(vault, note)
        if text is None:
            continue
        parents = parent_titles_from_text(text)
        new_parents = surviving_parents(parents) if any(title_key(p) in deleted_keys for p in parents) else None
        intermediate = set_parents(text, new_parents) if new_parents is not None else text
        removed = _count_links(intermediate, deleted_keys)
        if removed:
            plan.edits.append(FileEdit(note=_ref(note, dom.slug), links_removed=removed))
        if new_parents is not None:
            plan.reparent.append(ReparentChange(child=_ref(note, dom.slug), new_parents=new_parents))


async def apply_delete_plan(session: AsyncSession, plan: DeletePlan) -> None:
    """Rewrites other notes first, then removes files and index rows, so a crash
    can leave an extra file but never a dangling link. Safe to run twice."""
    slugs = sorted({ref.domain_slug for ref in plan.delete_notes})
    for slug in slugs:
        dom = await domain_repo.get_by_slug(session, slug)
        async with vault_lock(slug):
            await _apply_domain(session, dom, plan)
    await session.commit()


async def _apply_domain(session: AsyncSession, dom: Domain, plan: DeletePlan) -> None:
    vault = Path(dom.vault_path)
    doomed = [r for r in plan.delete_notes if r.domain_slug == dom.slug]
    deleted_keys = {title_key(r.title) for r in doomed}
    new_parents_by_id = {c.child.synapse_id: c.new_parents for c in plan.reparent if c.child.domain_slug == dom.slug}
    affected_ids = {e.note.synapse_id for e in plan.edits if e.note.domain_slug == dom.slug} | set(new_parents_by_id)

    rewritten: list[tuple[Note, str]] = []
    for note_id in affected_ids:
        try:
            note = await note_index_repo.get_note(session, note_id)
        except note_index_repo.NoteNotFoundError:
            continue
        text = _read(vault, note)
        if text is None:
            continue
        new_text = _rewrite(text, deleted_keys, new_parents_by_id.get(note_id))
        if new_text != text:
            note.content_hash = write_note_atomic(_note_path(vault, note), new_text)  # user_modified stays as it was
            rewritten.append((note, new_text))

    folders: set[Path] = set()
    for ref in doomed:
        path = resolve_in_vault(vault, *ref.path.split("/"))
        path.unlink(missing_ok=True)
        folders.add(path.parent)
        await note_index_repo.delete_note(session, ref.synapse_id)
        logger.info("note %r deleted from vault %r", ref.title, dom.slug)
    for folder in folders:
        if folder != vault.resolve():
            try:
                folder.rmdir()  # only succeeds when the topic folder is now empty
                logger.info("empty topic folder removed: %s", folder.name)
            except OSError:
                pass

    for note, new_text in rewritten:
        await reindex_note_links(session, note, new_text)
    logger.info(
        "vault %r: deleted %d note(s), stripped links in %d file(s), re-attached %d child(ren)",
        dom.slug, len(doomed), len(rewritten), len(new_parents_by_id),
    )

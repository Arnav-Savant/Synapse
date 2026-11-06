"""Thins the `## Related` sections of notes already in a vault. Preview first, then apply; only Related lines change.

Rule-based removals (no Claude): an entry that points at the note's own ancestor or descendant, which the hierarchy
links anyway, and the second copy of a pair that two notes list on each other. An optional review asks a small agent
which of the remaining entries a reader really needs (a prerequisite or a contrast); what it proposes is shown to the
owner and only removed if they confirm.

Works from the files on disk, as the delete service does, because the owner edits notes in Obsidian and the index
can lag. `apply_tidy` re-reads each file under the vault lock and is safe to run twice.
"""

import asyncio
import logging
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.link_pruner import RelatedEntry, prune_related
from app.db.models import Domain, Note
from app.engines.base import AgentEngine
from app.repositories import domain_repo, note_index_repo
from app.schemas.notes import NoteRef, TidyEdit, TidyPlan, TidyRemoval, TidyResult
from app.services.note_link_index import parent_titles_from_text, reindex_note_links
from app.services.related_links import pair_losers
from app.vault.assemble import related_entries, remove_related_entries
from app.vault.hierarchy import ParentMap, family
from app.vault.locks import vault_lock
from app.vault.paths import resolve_in_vault
from app.vault.store import write_note_atomic
from app.vault.titles import title_key

logger = logging.getLogger(__name__)

_REVIEW_PARALLEL = 4


def _read(vault: Path, note: Note) -> str | None:
    try:
        return resolve_in_vault(vault, *note.path.split("/")).read_text(encoding="utf-8")
    except FileNotFoundError:
        return None


async def _read_all(session: AsyncSession, domain: Domain) -> tuple[list[tuple[Note, str]], ParentMap]:
    vault = Path(domain.vault_path)
    files = [(n, t) for n in await note_index_repo.list_notes(session, domain.id) if (t := _read(vault, n)) is not None]
    tree: ParentMap = {title_key(n.title): {title_key(p) for p in parent_titles_from_text(t)} for n, t in files}
    return files, tree


def _rule_removals(files: list[tuple[Note, str]], tree: ParentMap) -> dict[str, list[str]]:
    """Per note id, the Related titles that the rules remove: implied by the tree, or the duplicate half of a pair."""
    kept: dict[str, list[tuple[str, str]]] = {}
    removed: dict[str, list[str]] = {}
    for note, text in files:
        implied = family(title_key(note.title), tree)
        entries = list(dict.fromkeys(related_entries(text)))
        removed[note.synapse_id] = [t for t, _ in entries if title_key(t) in implied]
        kept[title_key(note.title)] = [(t, n) for t, n in entries if title_key(t) not in implied]
    losers = pair_losers(kept)
    for note, _ in files:
        gone = losers.get(title_key(note.title), set())
        removed[note.synapse_id] += [t for t, _ in kept[title_key(note.title)] if title_key(t) in gone]
    return removed


def _ref(note: Note, slug: str) -> NoteRef:
    return NoteRef(synapse_id=note.synapse_id, title=note.title, path=note.path, domain_slug=slug, user_modified=note.user_modified)


async def build_tidy_plan(session: AsyncSession, domain_slug: str) -> TidyPlan:
    """No side effects, no Claude: which Related entries the rules remove."""
    domain = await domain_repo.get_by_slug(session, domain_slug)
    files, tree = await _read_all(session, domain)
    removals = _rule_removals(files, tree)
    edits = [TidyEdit(note=_ref(n, domain.slug), remove=removals[n.synapse_id]) for n, _ in files if removals[n.synapse_id]]
    edits.sort(key=lambda e: e.note.title.lower())
    return TidyPlan(domain_slug=domain.slug, edits=edits, links=sum(len(e.remove) for e in edits), reviewed=False, cost_usd=0.0)


async def review_tidy_plan(session: AsyncSession, engine: AgentEngine, domain_slug: str) -> TidyPlan:
    """The rule-based plan plus the agent's proposal for the entries that remain. Costs a small agent call per note."""
    domain = await domain_repo.get_by_slug(session, domain_slug)
    files, tree = await _read_all(session, domain)
    removals = _rule_removals(files, tree)
    summaries = {title_key(n.title): n.summary for n in await note_index_repo.list_notes(session, domain.id)}
    gate = asyncio.Semaphore(_REVIEW_PARALLEL)

    async def review(note: Note, text: str):
        gone = {title_key(t) for t in removals[note.synapse_id]}
        entries = [
            RelatedEntry(title=t, note=n, summary=summaries.get(title_key(t), ""))
            for t, n in dict.fromkeys(related_entries(text)) if title_key(t) not in gone
        ]
        if not entries:
            return note, [], 0.0
        async with gate:
            result = await prune_related(engine, run_id=f"tidy-{note.synapse_id[:8]}", note_title=note.title, note_summary=note.summary, entries=entries)
        return note, result.value, result.cost_usd

    results = await asyncio.gather(*(review(n, t) for n, t in files))
    edits, cost = [], 0.0
    for note, drop, spent in results:
        cost += spent
        if removals[note.synapse_id] or drop:
            edits.append(TidyEdit(note=_ref(note, domain.slug), remove=removals[note.synapse_id], review=drop))
    edits.sort(key=lambda e: e.note.title.lower())
    links = sum(len(e.remove) + len(e.review) for e in edits)
    logger.info("link review of vault %r: %d link(s) proposed for removal in %d note(s), cost $%.3f", domain.slug, links, len(edits), cost)
    return TidyPlan(domain_slug=domain.slug, edits=edits, links=links, reviewed=True, cost_usd=round(cost, 4))


async def apply_tidy(session: AsyncSession, domain_slug: str, extra: list[TidyRemoval]) -> TidyResult:
    """Removes the rule-based entries from every note, plus the agent-proposed ones the owner confirmed in `extra`."""
    domain = await domain_repo.get_by_slug(session, domain_slug)
    vault = Path(domain.vault_path)
    confirmed = {r.note_id: r.titles for r in extra}
    notes_changed = links_removed = 0
    async with vault_lock(domain.slug):
        files, tree = await _read_all(session, domain)
        removals = _rule_removals(files, tree)
        for note, text in files:
            present = {title_key(t): t for t, _ in related_entries(text)}
            drop = {title_key(t) for t in removals[note.synapse_id]} | {title_key(t) for t in confirmed.get(note.synapse_id, []) if title_key(t) in present}
            if not drop:
                continue
            updated = remove_related_entries(text, drop)
            if updated == text:
                continue
            note.content_hash = write_note_atomic(resolve_in_vault(vault, *note.path.split("/")), updated)  # user_modified stays as it was
            await reindex_note_links(session, note, updated)
            notes_changed += 1
            links_removed += len(drop)
    await session.commit()
    logger.info("vault %r: removed %d Related link(s) from %d note(s)", domain.slug, links_removed, notes_changed)
    return TidyResult(notes_changed=notes_changed, links_removed=links_removed)

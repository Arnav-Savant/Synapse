"""Turns approved outline nodes into note drafts (spec §8 steps 6-9, §10, §12, §20).

A draft is a complete, assembled note file held in Postgres until the owner approves it.
Agents only supply body sections; this module decides titles, folders, ids, parents and
links, and assembles the file. Everything here is safe to re-run: drafts are overwritten.
"""

import json
import logging
import posixpath
import uuid
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.linker import pick_related
from app.agents.reference_finder import find_references
from app.agents.researcher import research_node, verify_dossier
from app.agents.synthesizer import write_core, write_synthesis
from app.agents.validator import summarize_round, validate_note
from app.agents.writer import write_leaf
from app.db.models import Domain, Job, Note, NoteDraft
from app.engines.base import AgentEngine
from app.repositories import agent_config_repo, domain_repo, job_repo, note_draft_repo, note_index_repo, outline_draft_repo
from app.schemas.domains import DomainProfile
from app.schemas.dossier import Dossier, ResearchBudget
from app.schemas.outline import Outline, OutlineNode
from app.schemas.validation import Issue, NoteVerdict, RoundSummary
from app.services.draft_rules import check_draft_rules
from app.services.note_link_index import parent_titles_from_text
from app.vault.assemble import (
    NoteParts, assemble_note, carry_over_sections, insert_link_line, replace_body, set_parents, strip_link_sections,
)
from app.vault.frontmatter import split_frontmatter, with_meta
from app.vault.paths import resolve_in_vault
from app.vault.store import file_hash
from app.vault.titles import sanitize_title, title_key
from app.workflows.models import PlanInfo, PlanNode, round_key

logger = logging.getLogger(__name__)

_TOPIC_NAMESPACE = uuid.UUID("6f0d1a52-0a8e-4c57-9d5e-2b6e1f6f3a10")
_SOURCE_TITLE_UNSAFE = str.maketrans({"[": "(", "]": ")"})


@dataclass
class DraftContext:
    job: Job
    outline: Outline
    domains: dict[str, Domain]
    nodes: dict[str, OutlineNode] = field(default_factory=dict)
    children: dict[str, list[str]] = field(default_factory=dict)

    def profile(self, slug: str) -> DomainProfile:
        return DomainProfile.model_validate((self.job.profile_snapshot or {})[slug]["profile"])


async def load_context(session: AsyncSession, job_id: str) -> DraftContext:
    job = await job_repo.get_job(session, job_id)
    outline = await outline_draft_repo.get(session, job_id)
    if outline is None:
        raise ValueError("the job has no approved outline")
    domains = {slug: await domain_repo.get_by_slug(session, slug) for slug in job.resolved_domains}
    ctx = DraftContext(job=job, outline=outline, domains=domains)
    ctx.nodes = {n.key: n for n in outline.nodes}
    for n in outline.nodes:
        for parent in n.parent_keys:
            ctx.children.setdefault(parent, []).append(n.key)
    return ctx


def plan_info(ctx: DraftContext, max_parallel: int) -> PlanInfo:
    heights: dict[str, int] = {}

    def height(key: str) -> int:
        if key not in heights:
            kids = ctx.children.get(key, [])
            heights[key] = 0 if not kids else 1 + max(height(k) for k in kids)
        return heights[key]

    return PlanInfo(
        topic_mode=ctx.job.input_kind == "topic",
        max_parallel=max_parallel,
        nodes=[
            PlanNode(
                key=n.key, title=n.title, parent_keys=n.parent_keys, domains=n.domains,
                is_leaf=not ctx.children.get(n.key), height=height(n.key),
            )
            for n in ctx.outline.nodes
        ],
    )


# -- identity: titles, folders, parents ---------------------------------------------------------

async def merge_target(session: AsyncSession, node: OutlineNode, slug: str) -> Note | None:
    verdict = node.verdicts.get(slug)
    if verdict is None or verdict.kind != "same" or not verdict.target_note_id:
        return None
    try:
        return await note_index_repo.get_note(session, verdict.target_note_id)
    except note_index_repo.NoteNotFoundError:
        return None


async def effective_title(session: AsyncSession, node: OutlineNode, slug: str) -> str:
    target = await merge_target(session, node, slug)
    return target.title if target else sanitize_title(node.title)


async def folder_for(session: AsyncSession, ctx: DraftContext, node: OutlineNode, slug: str) -> str:
    """A merge keeps its file's folder. A node under a parent shares the parent's folder, so a
    topic's notes live together (an existing tree stays in its folder). A new top note starts its own."""
    target = await merge_target(session, node, slug)
    if target:
        return posixpath.dirname(target.path)
    for parent_key in node.parent_keys:
        parent = ctx.nodes[parent_key]
        if slug in parent.domains:
            return await folder_for(session, ctx, parent, slug)
    return sanitize_title(node.title)


async def parent_titles(session: AsyncSession, ctx: DraftContext, node: OutlineNode, slug: str) -> list[str]:
    return [
        await effective_title(session, ctx.nodes[pk], slug)
        for pk in node.parent_keys
        if slug in ctx.nodes[pk].domains
    ]


def _jsonable(meta: dict) -> dict:
    return json.loads(json.dumps(meta, default=str))


def _dossier_of(draft: NoteDraft | None) -> Dossier | None:
    if draft is None or not draft.dossier or "facts" not in draft.dossier:
        return None
    return Dossier.model_validate(draft.dossier)


async def _existing_draft(session: AsyncSession, job_id: str, domain_id: str, key: str) -> NoteDraft | None:
    try:
        return await note_draft_repo.get(session, job_id, domain_id, key)
    except note_draft_repo.NoteDraftNotFoundError:
        return None


# -- research and core ---------------------------------------------------------------------------

async def research_leaf(session: AsyncSession, engine: AgentEngine, ctx: DraftContext, node_key: str) -> float:
    """Topic-only. One dossier per leaf, shared by every domain the node targets."""
    node = ctx.nodes[node_key]
    config = await agent_config_repo.get_agent_config(session, "researcher")
    profiles = [(ctx.job.profile_snapshot[s]["name"], ctx.profile(s)) for s in node.domains]
    result = await research_node(
        engine, job_id=ctx.job.id, node=node, topic_title=ctx.outline.topic_title, profiles=profiles,
        budget=ResearchBudget.from_params(config.params),
    )
    dossier = await verify_dossier(result)
    for slug in node.domains:
        draft = await _existing_draft(session, ctx.job.id, ctx.domains[slug].id, node_key)
        keep = {"core": draft.dossier["core"]} if draft and draft.dossier and "core" in draft.dossier else {}
        await note_draft_repo.upsert(
            session, ctx.job.id, ctx.domains[slug].id, node_key,
            title=await effective_title(session, node, slug), dossier={**dossier.model_dump(), **keep}, stage="researched",
        )
    return result.cost_usd


async def write_shared_core(session: AsyncSession, engine: AgentEngine, ctx: DraftContext, node_key: str) -> float:
    """Cross-domain leaves: one domain-neutral core every domain's writer must preserve (spec §12)."""
    node = ctx.nodes[node_key]
    first = await _existing_draft(session, ctx.job.id, ctx.domains[node.domains[0]].id, node_key)
    result = await write_core(engine, job_id=ctx.job.id, node=node, dossier=_dossier_of(first))
    for slug in node.domains:
        draft = await _existing_draft(session, ctx.job.id, ctx.domains[slug].id, node_key)
        dossier = dict(draft.dossier or {}) if draft else {}
        dossier["core"] = result.value.core
        await note_draft_repo.upsert(
            session, ctx.job.id, ctx.domains[slug].id, node_key,
            title=await effective_title(session, node, slug), dossier=dossier,
            **({} if draft else {"stage": "researched"}),
        )
    return result.cost_usd


# -- writing -------------------------------------------------------------------------------------

async def write_draft(
    session: AsyncSession, engine: AgentEngine, ctx: DraftContext, node_key: str, slug: str, feedback: str | None
) -> float:
    """Writes (or rewrites) one node's note for one domain and saves the assembled file as its draft."""
    node, dom = ctx.nodes[node_key], ctx.domains[slug]
    vault, profile = Path(dom.vault_path), ctx.profile(slug)
    previous = await _existing_draft(session, ctx.job.id, dom.id, node_key)
    flags: list[dict] = []

    target = await merge_target(session, node, slug)
    existing_text = base_hash = None
    if target is not None:
        disk_path = resolve_in_vault(vault, *target.path.split("/"))
        try:
            existing_text, base_hash = disk_path.read_text(encoding="utf-8"), file_hash(disk_path)
        except FileNotFoundError:
            logger.warning("job %s: %r was to merge into %s, which no longer exists on disk; writing it as a new note", ctx.job.id[:8], node.title, target.path)
            flags.append({"code": "merge_target_missing", "message": f"The note {target.title!r} was deleted from disk, so this is written as a new note."})
            target = None

    title = target.title if target else sanitize_title(node.title)
    kids = [k for k in ctx.children.get(node_key, []) if slug in ctx.nodes[k].domains]
    prior_text = previous.body_md if previous is not None and previous.body_md and feedback else None

    if not kids:
        result = await write_leaf(
            engine, job_id=ctx.job.id, node=node, domain_slug=slug, profile=profile, dossier=_dossier_of(previous),
            core=(previous.dossier or {}).get("core") if previous else None,
            existing_text=existing_text, prior_draft=prior_text, feedback=feedback,
        )
    else:
        child_info: list[tuple[str, str]] = []
        for k in kids:
            child = await _existing_draft(session, ctx.job.id, ctx.domains[slug].id, k)
            summary = (child.frontmatter or {}).get("summary") if child else None
            child_info.append((await effective_title(session, ctx.nodes[k], slug), summary or ctx.nodes[k].summary))
        result = await write_synthesis(
            engine, job_id=ctx.job.id, node=node, domain_slug=slug, children=child_info, profile=profile,
            existing_text=existing_text, prior_draft=prior_text, feedback=feedback,
        )
    body = result.value
    parents = await parent_titles(session, ctx, node, slug)
    subtopics = [(await effective_title(session, ctx.nodes[k], slug), s) for k, (_, s) in zip(kids, child_info if kids else [])]

    if target is not None:
        text = _merge_into_existing(existing_text, body, parents, subtopics)
        synapse_id = target.synapse_id
    else:
        synapse_id = (previous.frontmatter or {}).get("synapse_id") if previous else None
        synapse_id = synapse_id or str(uuid.uuid4())
        meta = {
            "synapse_id": synapse_id,
            "topic_id": str(uuid.uuid5(_TOPIC_NAMESPACE, f"{ctx.job.id}:{node_key}")) if len(node.domains) > 1 else None,
            "domain": slug, "aliases": body.aliases, "summary": body.summary, "job_id": ctx.job.id, "created": date.today(),
        }
        text = assemble_note(NoteParts(title=title, meta=meta, body=body.render(), parents=parents, children=subtopics))
    if previous is not None and previous.body_md:
        text = carry_over_sections(previous.body_md, text)  # Related/References are not the writer's output

    folder = await folder_for(session, ctx, node, slug)
    path = target.path if target else (f"{folder}/{title}.md" if folder else f"{title}.md")
    resolve_in_vault(vault, *path.split("/"))  # refuses anything that would leave the vault

    saved_meta, _ = split_frontmatter(text)
    await note_draft_repo.upsert(
        session, ctx.job.id, dom.id, node_key,
        title=title, parents=parents, body_md=text, frontmatter=_jsonable(saved_meta),
        kind="merge" if target else "new", path=path, target_note_id=target.synapse_id if target else None,
        base_hash=base_hash, validator_flags=flags, stage="written",
    )
    logger.info(
        "job %s: draft %r for %r (%s, %d chars)", ctx.job.id[:8], title, slug,
        "merge into existing note" if target else "new note", len(text),
    )
    return result.cost_usd


def _merge_into_existing(existing_text: str, body, parents: list[str], subtopics: list[tuple[str, str]]) -> str:
    """Updated body in, owner's frontmatter, Up line and link blocks kept; new parents and subtopics are only added."""
    text = replace_body(existing_text, body.render())
    have = parent_titles_from_text(text)
    text = set_parents(text, have + [p for p in parents if title_key(p) not in {title_key(h) for h in have}])
    for entry in subtopics:
        text = insert_link_line(text, "Subtopics", entry)
    meta, _ = split_frontmatter(text)
    aliases = list(meta.get("aliases") or [])
    aliases += [a for a in body.aliases if title_key(a) not in {title_key(x) for x in aliases}]
    return with_meta(text, {"summary": body.summary or meta.get("summary", ""), "aliases": aliases})


# -- references, related links, validation ---------------------------------------------------------

async def add_references(session: AsyncSession, engine: AgentEngine, ctx: DraftContext, node_key: str) -> float:
    node = ctx.nodes[node_key]
    drafts = [d for s in node.domains if (d := await _existing_draft(session, ctx.job.id, ctx.domains[s].id, node_key))]
    if not drafts:
        return 0.0
    result = await find_references(engine, job_id=ctx.job.id, node=node, dossier=_dossier_of(drafts[0]))
    for draft in drafts:
        text = draft.body_md
        for ref in result.value.references:
            text = insert_link_line(text, "References", (f"[{ref.title.translate(_SOURCE_TITLE_UNSAFE)}]({ref.url})", ref.note))
        if text != draft.body_md:
            await note_draft_repo.upsert(session, ctx.job.id, draft.domain_id, node_key, body_md=text)
    return result.cost_usd


async def add_related(session: AsyncSession, engine: AgentEngine, job_id: str, draft_id: str) -> float:
    """Cross-links for one draft, from vault notes similar to it and from its sibling drafts."""
    drafts = await note_draft_repo.list_for_job(session, job_id)
    draft = next(d for d in drafts if d.id == draft_id)
    meta = draft.frontmatter or {}
    candidates = await note_index_repo.find_candidates(
        session, draft.domain_id, title=draft.title, aliases=list(meta.get("aliases") or []), summary=meta.get("summary") or ""
    )
    candidates = [c for c in candidates if c.note.synapse_id not in (draft.target_note_id, meta.get("synapse_id"))]
    hierarchy = {title_key(t) for t in draft.parents}
    siblings = [d.title for d in drafts if d.domain_id == draft.domain_id and d.id != draft.id and title_key(d.title) not in hierarchy]
    result = await pick_related(
        engine, job_id=job_id, note_title=draft.title, note_summary=meta.get("summary") or "",
        candidates=candidates, sibling_titles=siblings,
    )
    text = draft.body_md
    for link in result.value.links:
        if title_key(link.title) not in hierarchy:
            text = insert_link_line(text, "Related", (link.title, link.why))
    if text != draft.body_md:
        await note_draft_repo.upsert(session, job_id, draft.domain_id, draft.node_key, body_md=text)
    return result.cost_usd


async def check_draft(
    session: AsyncSession, engine: AgentEngine, ctx: DraftContext, draft: NoteDraft, siblings: set[str]
) -> tuple[NoteVerdict, float]:
    """Rule checks, a title-collision check, then the Validator agent."""
    vault_titles = {n.title for n in await note_index_repo.list_notes(session, draft.domain_id)}
    issues = check_draft_rules(title=draft.title, text=draft.body_md, vault_titles=vault_titles, sibling_titles=siblings)
    clash = await note_index_repo.find_by_title_key(session, draft.domain_id, draft.title)
    if draft.kind == "new" and clash is not None and clash.synapse_id != (draft.frontmatter or {}).get("synapse_id"):
        issues.append(Issue(code="title_exists", message=f"A note titled {draft.title!r} already exists in this vault; it cannot be created again."))
    node = ctx.nodes[draft.node_key]
    slug = next(s for s, d in ctx.domains.items() if d.id == draft.domain_id)
    result = await validate_note(
        engine, job_id=ctx.job.id, note_text=strip_link_sections(draft.body_md), node=node, profile=ctx.profile(slug),
        dossier=_dossier_of(draft),
    )
    issues += result.value.issues
    return NoteVerdict(ok=not issues, issues=issues), result.cost_usd


async def validate_drafts(
    session: AsyncSession, engine: AgentEngine, ctx: DraftContext, only_keys: list[str] | None, previous: dict[str, list[str]]
) -> tuple[RoundSummary, float]:
    drafts = await note_draft_repo.list_for_job(session, ctx.job.id)
    slug_of = {d.id: s for s, d in ctx.domains.items()}
    wanted = [d for d in drafts if only_keys is None or round_key(d.node_key, slug_of[d.domain_id]) in only_keys]
    verdicts: dict[str, NoteVerdict] = {}
    total = 0.0
    for draft in wanted:
        siblings = {d.title for d in drafts if d.domain_id == draft.domain_id}
        verdict, cost = await check_draft(session, engine, ctx, draft, siblings)
        total += cost
        verdicts[round_key(draft.node_key, slug_of[draft.domain_id])] = verdict
        await note_draft_repo.upsert(
            session, ctx.job.id, draft.domain_id, draft.node_key,
            validator_flags=[i.model_dump() for i in verdict.issues] + [f for f in draft.validator_flags if f.get("code") == "merge_target_missing"],
            stage="validated",
        )
    summary = summarize_round(verdicts, {k: set(v) for k, v in previous.items()})
    logger.info(
        "job %s: validated %d draft(s): %d failing%s", ctx.job.id[:8], len(verdicts), len(summary.failing_keys),
        " (no progress since the last round)" if summary.no_progress else "",
    )
    return summary, total

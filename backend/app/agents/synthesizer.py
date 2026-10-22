"""Synthesizer: parent and top notes that compare their children, and the shared core for twin notes."""

import logging

from pydantic import BaseModel

from app.agents.prompt_parts import dossier_block, profile_block
from app.agents.runner import RunResult, run_structured
from app.agents.writer import _revision_block, body_model_for
from app.engines.base import AgentEngine
from app.schemas.domains import DomainProfile
from app.schemas.dossier import Dossier
from app.schemas.note_body import NoteBody, clean_body
from app.schemas.outline import OutlineNode

logger = logging.getLogger(__name__)


async def write_synthesis(
    engine: AgentEngine,
    *,
    job_id: str,
    node: OutlineNode,
    domain_slug: str,
    children: list[tuple[str, str]],
    profile: DomainProfile,
    existing_text: str | None = None,
    prior_draft: str | None = None,
    feedback: str | None = None,
    hub: bool = False,
    top: bool | None = None,
) -> RunResult[NoteBody]:
    """`children` is (title, one-line summary) of what was actually written. The
    Subtopics list is added by code, so the body must not list the children."""
    is_top = (not node.parent_keys) if top is None else top  # the top note of a topic, which may itself sit under a hub
    role_text = (
        "This is a HUB note: a short orientation to one area of the domain that groups related topics. Say what the area "
        "covers, why it is worth studying as a whole, and how its topics relate or in what order to read them. Keep it "
        "brief (a few paragraphs at most); the topics themselves hold the detail."
        if hub
        else
        "This is the TOP note of the topic: frame it. Give the big picture, why the topic matters, how its groups of "
        "subtopics relate to each other, and a suggested reading order."
        if is_top
        else "This is a PARENT note: it synthesizes its group. Say what the group is and why it exists, and above all "
        "how the children differ and compare (a comparison table is welcome)."
    )
    child_lines = "\n".join(f"- {t}: {s}" for t, s in children) or "(none)"
    prompt = (
        f"You write one synthesis note for the '{domain_slug}' vault.\n\n"
        f"Note title: {node.title}\nWhat it covers: {node.summary}\n\n{profile_block([(domain_slug, profile)])}\n\n"
        f"{role_text}\n\nThe children already written:\n{child_lines}\n\n"
        "Do NOT re-explain what the children cover; they explain themselves. Give just enough that the reader knows "
        "what each child is and when to read it. Do not write a list of the children (a Subtopics list is generated), "
        "and do not write Up, Related or References sections or links to other notes. Use `##` section headings of "
        "your choice."
    )
    revision = _revision_block(existing_text, prior_draft, feedback)
    if revision:
        prompt += f"\n\n{revision}"
    result = await run_structured(
        engine, role="synthesizer", job_id=job_id, prompt=prompt, model_cls=body_model_for(None), timeout_seconds=600
    )
    body, changed = clean_body(result.value)
    if changed:
        logger.warning("job %s: synthesizer for %r returned reserved headings; stripped", job_id[:8], node.title)
    logger.info("job %s: synthesized %r for %r over %d child(ren)", job_id[:8], node.title, domain_slug, len(children))
    return RunResult(value=body, cost_usd=result.cost_usd, fetched_urls=result.fetched_urls)


class CoreText(BaseModel):
    core: str


async def write_core(
    engine: AgentEngine, *, job_id: str, node: OutlineNode, dossier: Dossier | None
) -> RunResult[CoreText]:
    """A short, domain-neutral statement of the node's essence. Every domain's writer gets it as
    the invariant, so twin notes never drift apart."""
    material = (
        dossier_block(dossier)
        if dossier is not None
        else f"Material supplied by the owner:\n<<<\n{node.content_slice or ''}\n>>>"
    )
    prompt = (
        "Write the shared core of a study note that will be written once per knowledge domain, each from its own angle. "
        "The core is the part that must stay true in every version: what the subject is, how it works in essence, and "
        "its key trade-offs. Domain-neutral, 150 to 300 words, no headings.\n\n"
        f"Subject: {node.title}\nWhat it covers: {node.summary}\n\n{material}"
    )
    result = await run_structured(engine, role="synthesizer", job_id=job_id, prompt=prompt, model_cls=CoreText)
    logger.info("job %s: wrote the shared core for %r", job_id[:8], node.title)
    return result

"""Writer: leaf notes in full depth, domain-lens versions, and merges into existing notes."""

import logging

from pydantic import create_model, model_validator

from app.agents.prompt_parts import dossier_block, profile_block
from app.agents.runner import RunResult, run_structured
from app.engines.base import AgentEngine
from app.schemas.domains import DomainProfile
from app.schemas.dossier import Dossier
from app.schemas.note_body import NoteBody, clean_body
from app.schemas.outline import OutlineNode

logger = logging.getLogger(__name__)


def section_heading(depth_section: str) -> str:
    """A profile depth section reads 'Foundations: what it is, the problem...'; the heading is the part before the colon."""
    return depth_section.split(":", 1)[0].strip()


def body_model_for(headings: list[str] | None) -> type[NoteBody]:
    """NoteBody, restricted to the profile's headings (case-insensitive) when there are any.
    Headings come back in the profile's order; at least one section must have text."""
    allowed = {h.lower(): h for h in headings or []}

    def check(self: NoteBody) -> NoteBody:
        if not any(t.strip() for t in self.sections.values()):
            raise ValueError("`sections` must contain at least one section with text")
        if allowed:
            unknown = [h for h in self.sections if h.strip().lower() not in allowed]
            if unknown:
                raise ValueError(f"unknown section heading(s) {unknown}; use only {list(allowed.values())}")
            by_key = {h.strip().lower(): t for h, t in self.sections.items()}
            self.sections = {allowed[k]: by_key[k] for k in allowed if k in by_key}
        return self

    return create_model("NoteBodyOut", __base__=NoteBody, __validators__={"check": model_validator(mode="after")(check)})


def _revision_block(existing_text: str | None, prior_draft: str | None, feedback: str | None) -> str:
    parts: list[str] = []
    if existing_text:
        parts.append(
            "A note on this subject already exists in the vault, exactly as it is on disk now (including edits the owner "
            "made by hand). Produce its UPDATED body: keep everything accurate that is already there, keep the owner's "
            "own wording and additions, and fold the new material in where it belongs. Do not discard existing "
            "sections. Ignore its frontmatter and the Up/Subtopics/Related/References blocks; those are handled "
            f"separately.\n<<<existing note\n{existing_text}\n>>>"
        )
    if prior_draft:
        parts.append(f"This is your previous draft; revise it rather than starting over:\n<<<previous draft\n{prior_draft}\n>>>")
    if feedback:
        parts.append(f"Feedback to apply:\n{feedback}")
    return "\n\n".join(parts)


async def write_leaf(
    engine: AgentEngine,
    *,
    job_id: str,
    node: OutlineNode,
    domain_slug: str,
    profile: DomainProfile,
    dossier: Dossier | None,
    core: str | None = None,
    existing_text: str | None = None,
    prior_draft: str | None = None,
    feedback: str | None = None,
) -> RunResult[NoteBody]:
    headings = [section_heading(s) for s in profile.depth_sections]
    if existing_text or not headings:
        # a merge keeps whatever sections the note already has; a profile with no template leaves headings to the writer
        model_cls = body_model_for(None)
        template = (
            "Choose clear `##`-level section headings that suit the subject."
            if not headings
            else "Keep the note's existing section headings and add new sections only where the new material needs them."
        )
    else:
        model_cls = body_model_for(headings)
        guide = "\n".join(f"- {s}" for s in profile.depth_sections)
        template = (
            "Structure the note with these sections, in this order, using exactly these headings. Omit a section that "
            f"has no real substance for this subject, and never pad one:\n{guide}"
        )

    material = (
        f"Research dossier to write from:\n{dossier_block(dossier)}"
        if dossier is not None
        else f"Material supplied by the owner for this note (primary source; add accurate explanation where it is silent):\n<<<\n{node.content_slice or ''}\n>>>"
    )
    prompt = (
        f"You write one study note, for the '{domain_slug}' vault.\n\n"
        f"Note title: {node.title}\nWhat it covers: {node.summary}\n\n{profile_block([(domain_slug, profile)])}\n\n"
        f"{template}\n\n"
        "Explain mechanisms, not just definitions. Be concrete: examples, step-by-step flows, trade-offs. Use `###` for "
        "sub-headings. Do not write Up, Subtopics, Related or References sections and do not add links to other notes; "
        "those are generated for you. Do not invent facts the material does not support; where it is silent, say what is "
        "version- or configuration-dependent instead of guessing.\n\n"
        f"{material}\n"
    )
    if core:
        prompt += (
            f"\nShared essence: every domain's version of this note must preserve the following. Write it through the "
            f"lens of the '{domain_slug}' domain, briefly naming the other domains' concerns where they touch it.\n<<<core\n{core}\n>>>\n"
        )
    revision = _revision_block(existing_text, prior_draft, feedback)
    if revision:
        prompt += f"\n{revision}\n"

    result = await run_structured(engine, role="writer", job_id=job_id, prompt=prompt, model_cls=model_cls, timeout_seconds=900)
    body, changed = clean_body(result.value)
    if changed:
        logger.warning("job %s: writer for %r returned reserved headings (Up/Subtopics/Related/References); stripped", job_id[:8], node.title)
    logger.info("job %s: wrote %r for %r (%d section(s))", job_id[:8], node.title, domain_slug, len(body.sections))
    return RunResult(value=body, cost_usd=result.cost_usd, fetched_urls=result.fetched_urls)

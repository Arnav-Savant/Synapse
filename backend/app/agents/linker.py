"""Linker: overlap verdicts for outline nodes, and `## Related` links for notes."""

import logging
from typing import Literal

from pydantic import BaseModel, Field, create_model, model_validator

from app.agents.runner import RunResult, run_structured
from app.engines.base import AgentEngine
from app.repositories.note_index_repo import Candidate
from app.schemas.outline import OutlineNode, OverlapVerdict
from app.vault.titles import title_key

logger = logging.getLogger(__name__)

_SLICE_DIGEST_CHARS = 1500
MAX_RELATED = 8


class _OverlapChoice(BaseModel):
    kind: Literal["same", "partial", "distinct"]
    target_note_id: str | None = None
    reason: str = ""

    @model_validator(mode="after")
    def _target_matches_kind(self) -> "_OverlapChoice":
        if self.kind != "distinct" and not self.target_note_id:
            raise ValueError(f"a {self.kind!r} verdict must name target_note_id, one of the candidate ids")
        if self.kind == "distinct":
            self.target_note_id = None
        return self


def _candidate_block(candidates: list[Candidate]) -> str:
    lines = []
    for c in candidates:
        aliases = f" (also called: {', '.join(c.note.aliases)})" if c.note.aliases else ""
        lines.append(f"- id {c.note.synapse_id}: {c.note.title}{aliases}: {c.note.summary or '(no summary)'}")
    return "\n".join(lines)


async def judge_overlap(
    engine: AgentEngine, *, job_id: str, node: OutlineNode, domain: str, candidates: list[Candidate]
) -> RunResult[OverlapVerdict]:
    """No candidates means nothing can overlap: `distinct`, and the engine is never called."""
    if not candidates:
        return RunResult(value=OverlapVerdict(kind="distinct", reason="no similar notes in this vault"), cost_usd=0.0, fetched_urls=())

    ids = tuple(c.note.synapse_id for c in candidates)
    choice_cls = create_model(
        "OverlapChoice", __base__=_OverlapChoice, target_note_id=(Literal[ids] | None, None)  # type: ignore[valid-type]
    )
    digest = (node.content_slice or "")[:_SLICE_DIGEST_CHARS]
    prompt = (
        f"You decide whether a planned note duplicates a note that already exists in the '{domain}' vault.\n\n"
        f"Planned note: {node.title}\nSummary: {node.summary or '(none)'}\n"
        + (f"Material it will be written from (excerpt):\n{digest}\n" if digest else "")
        + f"\nExisting notes that look similar:\n{_candidate_block(candidates)}\n\n"
        "Verdict, judged on meaning rather than wording:\n"
        "- same: the planned note is the same subject as that existing note. It should be merged into it.\n"
        "- partial: related and overlapping, but a genuinely separate note is warranted. It will link to the existing one.\n"
        "- distinct: none of them is really the same subject.\n"
        "For same or partial set `target_note_id` to that note's id. `reason` is one short sentence."
    )
    result = await run_structured(engine, role="linker", job_id=job_id, prompt=prompt, model_cls=choice_cls)
    verdict = OverlapVerdict(kind=result.value.kind, target_note_id=result.value.target_note_id, reason=result.value.reason)
    logger.info("job %s: overlap for %r in %r: %s%s", job_id[:8], node.title, domain, verdict.kind, f" ({verdict.reason})" if verdict.reason else "")
    return RunResult(value=verdict, cost_usd=result.cost_usd, fetched_urls=result.fetched_urls)


class RelatedLink(BaseModel):
    title: str
    why: str = Field(description="one line on how the notes relate")


class RelatedList(BaseModel):
    links: list[RelatedLink]


async def pick_related(
    engine: AgentEngine,
    *,
    job_id: str,
    note_title: str,
    note_summary: str,
    candidates: list[Candidate],
    sibling_titles: list[str],
) -> RunResult[RelatedList]:
    """Cross-links for `## Related`. Titles that are not among the inputs are dropped."""
    allowed = {title_key(c.note.title): c.note.title for c in candidates}
    allowed.update({title_key(t): t for t in sibling_titles})
    allowed.pop(title_key(note_title), None)
    if not allowed:
        return RunResult(value=RelatedList(links=[]), cost_usd=0.0, fetched_urls=())

    options = _candidate_block(candidates)
    siblings = "\n".join(f"- {t}" for t in sibling_titles if title_key(t) != title_key(note_title))
    prompt = (
        "You choose the cross-links for the `Related` section of a study note, so the notes form a dense, useful graph.\n\n"
        f"Note: {note_title}\nSummary: {note_summary}\n\n"
        + (f"Existing notes in the vault:\n{options}\n\n" if options else "")
        + (f"Other notes being written in the same batch:\n{siblings}\n\n" if siblings else "")
        + f"Pick up to {MAX_RELATED} of the listed notes that a reader of this note would genuinely want next: prerequisites, "
        "contrasts, alternatives, deeper dives. Use each title exactly as listed. Skip weak links; an empty list is fine. "
        "Do not include this note itself."
    )
    result = await run_structured(engine, role="linker", job_id=job_id, prompt=prompt, model_cls=RelatedList)
    seen: set[str] = set()
    links: list[RelatedLink] = []
    for link in result.value.links:
        key = title_key(link.title)
        if key in allowed and key not in seen:
            seen.add(key)
            links.append(RelatedLink(title=allowed[key], why=link.why))
    dropped = len(result.value.links) - len(links)
    if dropped:
        logger.warning("job %s: dropped %d related link(s) for %r that were not among the offered notes", job_id[:8], dropped, note_title)
    return RunResult(value=RelatedList(links=links[:MAX_RELATED]), cost_usd=result.cost_usd, fetched_urls=result.fetched_urls)

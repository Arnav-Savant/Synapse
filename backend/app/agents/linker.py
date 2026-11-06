"""Linker: overlap verdicts for outline nodes, and `## Related` links for notes."""

import logging
import re
from typing import Literal

from pydantic import BaseModel, Field, create_model, model_validator

from app.agents.runner import RunResult, run_structured
from app.engines.base import AgentEngine
from app.repositories.note_index_repo import Candidate
from app.schemas.outline import OutlineNode, OverlapVerdict
from app.vault.titles import title_key

logger = logging.getLogger(__name__)

_SLICE_DIGEST_CHARS = 1500
_GENERIC_REASON = re.compile(r"^(a |an |the )?(closely |also |highly |directly |broadly )?(related|similar|relevant)\b[\w\s]{0,20}$", re.IGNORECASE)
_MIN_REASON_WORDS = 4


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
        "- partial: related and overlapping, but a genuinely separate note is warranted. The new note is offered the existing one as a possible cross-link.\n"
        "- distinct: none of them is really the same subject.\n"
        "For same or partial set `target_note_id` to that note's id. `reason` is one short sentence."
    )
    result = await run_structured(engine, role="linker", job_id=job_id, prompt=prompt, model_cls=choice_cls)
    verdict = OverlapVerdict(kind=result.value.kind, target_note_id=result.value.target_note_id, reason=result.value.reason)
    logger.info("job %s: overlap for %r in %r: %s%s", job_id[:8], node.title, domain, verdict.kind, f" ({verdict.reason})" if verdict.reason else "")
    return RunResult(value=verdict, cost_usd=result.cost_usd, fetched_urls=result.fetched_urls)


class RelatedLink(BaseModel):
    title: str
    kind: Literal["prerequisite", "contrast"] = Field(
        description="prerequisite: read the other note first; contrast: the direct alternative or counterpart to tell this note apart from"
    )
    why: str = Field(description="one sentence: what the reader needs from the other note, or how the two differ")

    @property
    def entry_note(self) -> str:
        return f"{self.kind.capitalize()}: {self.why.strip()}"


class RelatedList(BaseModel):
    links: list[RelatedLink]


def _has_real_reason(why: str) -> bool:
    """A link must say why. An empty line or a bare "related" / "similar topic" is not a reason."""
    text = why.strip()
    return len(text.split()) >= _MIN_REASON_WORDS and not _GENERIC_REASON.match(text)


async def pick_related(
    engine: AgentEngine,
    *,
    job_id: str,
    note_title: str,
    note_summary: str,
    candidates: list[Candidate],
    sibling_titles: list[str],
) -> RunResult[RelatedList]:
    """Cross-links for `## Related`. `candidates` and `sibling_titles` are already free of the note's ancestors and
    descendants, which the hierarchy links anyway. Titles that are not among the inputs are dropped, and so is a
    link that gives no real reason. There is no cap on how many links a note may have."""
    allowed = {title_key(c.note.title): c.note.title for c in candidates}
    allowed.update({title_key(t): t for t in sibling_titles})
    allowed.pop(title_key(note_title), None)
    if not allowed:
        return RunResult(value=RelatedList(links=[]), cost_usd=0.0, fetched_urls=())

    options = _candidate_block(candidates)
    siblings = "\n".join(f"- {t}" for t in sibling_titles if title_key(t) != title_key(note_title))
    prompt = (
        "You choose the cross-links for the `Related` section of a study note.\n\n"
        f"Note: {note_title}\nSummary: {note_summary}\n\n"
        + (f"Existing notes in the vault:\n{options}\n\n" if options else "")
        + (f"Other notes being written in the same batch:\n{siblings}\n\n" if siblings else "")
        + "The note's parents, children and the notes above and below it are already linked by the hierarchy and are not "
        "listed. Keep the graph sparse: a cross-link is allowed only for one of two reasons.\n"
        "- prerequisite: the reader must understand the other note before this one makes sense.\n"
        "- contrast: the other note is the direct alternative or counterpart this note must be told apart from.\n"
        "Being in the same area, sharing a parent, or being useful background is not enough; notes under one parent are "
        "already one click apart through it. When in doubt, leave the link out. Most notes need none or one, and an empty "
        "list is the expected answer. Use each title exactly as listed, and do not include this note itself. `why` is one "
        "sentence."
    )
    result = await run_structured(engine, role="linker", job_id=job_id, prompt=prompt, model_cls=RelatedList)
    seen: set[str] = set()
    links: list[RelatedLink] = []
    unknown = unreasoned = 0
    for link in result.value.links:
        key = title_key(link.title)
        if key not in allowed:
            unknown += 1
        elif not _has_real_reason(link.why):
            unreasoned += 1
        elif key not in seen:
            seen.add(key)
            links.append(RelatedLink(title=allowed[key], kind=link.kind, why=link.why.strip()))
    if unknown or unreasoned:
        logger.warning(
            "job %s: for %r dropped %d related link(s) not among the offered notes and %d with no real reason",
            job_id[:8], note_title, unknown, unreasoned,
        )
    return RunResult(value=RelatedList(links=links), cost_usd=result.cost_usd, fetched_urls=result.fetched_urls)

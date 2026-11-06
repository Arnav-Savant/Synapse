"""Link pruner: of one note's `Related` entries, keeps only the ones a reader really needs."""

import logging
from dataclasses import dataclass

from pydantic import BaseModel, Field, model_validator

from app.agents.runner import RunResult, run_structured
from app.engines.base import AgentEngine
from app.vault.titles import title_key

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RelatedEntry:
    title: str
    note: str  # the reason written after the link
    summary: str  # what the linked note covers


class Kept(BaseModel):
    keep: list[str] = Field(description="titles of the entries worth keeping, copied exactly; empty when none is")


async def prune_related(
    engine: AgentEngine, *, run_id: str, note_title: str, note_summary: str, entries: list[RelatedEntry]
) -> RunResult[list[str]]:
    """Returns the titles to remove. Every other entry is kept. A title the agent invents is ignored."""
    by_key = {title_key(e.title): e for e in entries}

    class _Kept(Kept):
        @model_validator(mode="after")
        def _known(self) -> "_Kept":
            unknown = [t for t in self.keep if title_key(t) not in by_key]
            if unknown:
                raise ValueError(f"these titles are not among the entries: {unknown}")
            return self

    lines = "\n".join(f"- {e.title}: covers {e.summary or '(no summary)'}. Reason given: {e.note or '(none)'}" for e in entries)
    prompt = (
        "You keep a study note's cross-links sparse. A `Related` link is worth keeping only for one of two reasons:\n"
        "- prerequisite: the reader must understand the other note before this one makes sense.\n"
        "- contrast: the other note is the direct alternative or counterpart this note must be told apart from.\n"
        "Being in the same area, sharing a parent, or being useful background is not enough. When in doubt, drop it.\n\n"
        f"Note: {note_title}\nSummary: {note_summary or '(none)'}\n\nIts Related entries:\n{lines}\n\n"
        "Return the titles to keep, copied exactly. An empty list is fine."
    )
    result = await run_structured(engine, role="link_pruner", job_id=run_id, prompt=prompt, model_cls=_Kept)
    kept = {title_key(t) for t in result.value.keep}
    drop = [e.title for e in entries if title_key(e.title) not in kept]
    logger.info("link review for %r: keeping %d of %d Related link(s)", note_title, len(entries) - len(drop), len(entries))
    return RunResult(value=drop, cost_usd=result.cost_usd, fetched_urls=result.fetched_urls)

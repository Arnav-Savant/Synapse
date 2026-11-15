"""Reader: pulls the passages that matter for a goal out of the notes it is given, quoted exactly."""

import logging
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from app.agents.prompt_parts import UNTRUSTED_NOTES
from app.agents.runner import RunResult, run_structured
from app.engines.base import AgentEngine
from app.schemas.chat_agents import NoteText, Passage, ToolRecord, log_block
from app.vault.titles import title_key

logger = logging.getLogger(__name__)


class ReadNote(BaseModel):
    action: Literal["read_note"]
    domain: str
    title: str


class ReaderFinish(BaseModel):
    action: Literal["finish"]
    passages: list[Passage]


class ReaderReply(BaseModel):
    step: Annotated[ReadNote | ReaderFinish, Field(discriminator="action")]


def _collapse(s: str) -> str:
    return " ".join(s.split())


async def reader_step(
    engine: AgentEngine,
    *,
    run_id: str,
    goal: str,
    notes: list[NoteText],
    log: list[ToolRecord],
    max_steps: int = 3,
) -> RunResult[ReadNote | ReaderFinish]:
    """One call of a reader run. The runtime carries out `read_note`, adds the note to `notes` and calls again."""
    by_note = {(n.domain, title_key(n.title)): _collapse(n.text) for n in notes}

    class _Reply(ReaderReply):
        @model_validator(mode="after")
        def _quoted(self) -> "_Reply":
            if isinstance(self.step, ReaderFinish):
                for p in self.step.passages:
                    text = by_note.get((p.domain, title_key(p.title)))
                    if text is None:
                        raise ValueError(f"{p.title} ({p.domain}) is not one of the notes you were given")
                    if _collapse(p.excerpt) not in text:
                        raise ValueError(
                            f"the excerpt from {p.title} does not occur in the note; quote the note exactly, "
                            f"word for word, without paraphrasing: {p.excerpt[:80]!r}"
                        )
            return self

    note_text = "\n\n".join(f"=== {n.domain} / {n.title} ===\n{n.text}" for n in notes) or "(no notes)"
    prompt = (
        "You are a reader in a study chat. Extract the passages of the notes below that matter for the goal.\n"
        "Return each passage as a verbatim excerpt (copied word for word, never paraphrased or stitched together) "
        "with the heading it sits under, or an empty heading if it sits under none. Prefer a few focused excerpts "
        "over long ones. If a note links to another note worth following, you may `read_note` it.\n"
        f"{UNTRUSTED_NOTES}\n\n"
        f"Goal: {goal}\n\n"
        f"Notes:\n{note_text}\n\n"
        f"What you have done so far in this run:\n{log_block(log)}\n\n"
        f"Step budget: this is step {len(log) + 1} of {max_steps}. On the last step you must `finish`."
    )
    result = await run_structured(engine, role="reader", job_id=run_id, prompt=prompt, model_cls=_Reply)
    step = result.value.step
    logger.info("reader step %d: %s", len(log) + 1, step.action)
    return RunResult(value=step, cost_usd=result.cost_usd, fetched_urls=result.fetched_urls)

"""Chat orchestrator: decides each step of a turn: send a subagent, recall evidence, ask the owner, or answer."""

import logging
import re
from dataclasses import dataclass
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

from app.agents.prompt_parts import UNTRUSTED_NOTES
from app.agents.runner import RunResult, run_structured
from app.engines.base import AgentEngine
from app.schemas.chat_agents import NoteRef, ToolRecord, log_block

logger = logging.getLogger(__name__)

_CITATION = re.compile(r"\[E(\d+)\]")


class ReaderTask(BaseModel):
    notes: list[NoteRef] = Field(min_length=1, max_length=12)
    goal: str = Field(description="what to extract, written so it stands on its own")


class DelegateNavigator(BaseModel):
    action: Literal["delegate_navigator"]
    task: str = Field(description="what to find, written so it stands on its own")


class DelegateReaders(BaseModel):
    action: Literal["delegate_readers"]
    tasks: list[ReaderTask] = Field(min_length=1, max_length=4)


class Recall(BaseModel):
    action: Literal["recall"]
    refs: list[int] = Field(min_length=1, description="evidence numbers whose full text you need again")


class AskOwner(BaseModel):
    action: Literal["ask_owner"]
    question: str = Field(min_length=1)


class Answer(BaseModel):
    action: Literal["answer"]
    text: str = Field(min_length=1)
    gaps: list[str] = Field(description="concepts the question needs that the notes do not cover")


class OrchestratorReply(BaseModel):
    step: Annotated[DelegateNavigator | DelegateReaders | Recall | AskOwner | Answer, Field(discriminator="action")]


class FinalReply(BaseModel):
    step: Annotated[AskOwner | Answer, Field(discriminator="action")]


@dataclass
class EvidenceView:
    """One piece of evidence the chat holds. `excerpt` is None when it is listed by reference only."""

    ref: int
    domain: str
    title: str
    heading: str
    excerpt: str | None


@dataclass
class OrchestratorContext:
    domains: list[str]
    summary: str
    recent: list[tuple[str, str]]  # (role, text), oldest first
    evidence: list[EvidenceView]
    question: str
    log: list[ToolRecord]
    steps_left: int
    verifier_issues: list[str]


def _evidence_block(evidence: list[EvidenceView]) -> str:
    if not evidence:
        return "(none yet)"
    lines: list[str] = []
    for e in evidence:
        where = f"{e.title} ({e.domain})" + (f" § {e.heading}" if e.heading else "")
        if e.excerpt is None:
            lines.append(f"[E{e.ref}] {where}: held by reference only; use `recall` to read it again")
        else:
            lines.append(f"[E{e.ref}] {where}:\n{e.excerpt}")
    return "\n\n".join(lines)


async def orchestrator_step(
    engine: AgentEngine, *, run_id: str, ctx: OrchestratorContext, final: bool
) -> RunResult[DelegateNavigator | DelegateReaders | Recall | AskOwner | Answer]:
    """One call of the orchestrator. The runtime carries out the action and calls again with the updated context."""
    known = {e.ref for e in ctx.evidence}
    base = FinalReply if final else OrchestratorReply

    class _Reply(base):  # type: ignore[valid-type, misc]
        @model_validator(mode="after")
        def _refs_known(self) -> "_Reply":
            step = self.step
            if isinstance(step, Answer):
                unknown = sorted({int(n) for n in _CITATION.findall(step.text)} - known)
                if unknown:
                    raise ValueError(
                        f"the answer cites evidence that does not exist: {['E%d' % n for n in unknown]}; "
                        f"the evidence held is {['E%d' % n for n in sorted(known)] or 'empty'}"
                    )
            elif isinstance(step, Recall):
                unknown = sorted(set(step.refs) - known)
                if unknown:
                    raise ValueError(f"recall names evidence that does not exist: {unknown}")
            return self

    recent = "\n".join(f"{role}: {text}" for role, text in ctx.recent) or "(no earlier messages)"
    issues = (
        "\n\nThe verifier rejected your last draft for these reasons. Fix them (fetch more evidence or rewrite):\n"
        + "\n".join(f"- {i}" for i in ctx.verifier_issues)
        if ctx.verifier_issues
        else ""
    )
    if final:
        ending = (
            "Your steps are used up. This is your final call: you may only `answer` with what the evidence supports "
            "(listing what it does not cover under `gaps`) or `ask_owner` a clarifying question."
        )
    else:
        ending = (
            f"You have {ctx.steps_left} action(s) left this turn. Actions: `delegate_navigator` (find notes), "
            "`delegate_readers` (extract passages from notes, up to 4 tasks in parallel), `recall` (read earlier evidence "
            "again), `ask_owner` (ask a clarifying question, ending the turn), `answer` (send a draft to the verifier)."
        )
    prompt = (
        "You are the orchestrator of a study chat. You answer the owner's question from their own notes, and you decide "
        "each step yourself. Subagents never talk to each other or see this conversation: every handover goes through you. "
        "You may drop a navigator's picks, add your own, re-send the navigator, or skip reading when the evidence you "
        "already hold is enough.\n\n"
        "Rules:\n"
        "- Cite. Every statement drawn from the notes carries its evidence number like [E3]. Anything not from the notes "
        "must be introduced as general knowledge, not cited. Concepts the notes do not cover go under `gaps`.\n"
        "- A task for a subagent must stand on its own: resolve words like \"it\" and \"that\" from the conversation.\n"
        "- A question may be a scenario whose answer lies in notes it never names (for example, how a sign-up form checks "
        "that a username is free is answered by a note on Bloom filters). Reason about the concepts underneath it.\n"
        "- Every draft is checked by a verifier against the evidence it cites.\n"
        f"{UNTRUSTED_NOTES}\n\n"
        f"Vaults in this chat: {', '.join(ctx.domains) or '(none)'}\n\n"
        f"Summary of the older conversation:\n{ctx.summary or '(none)'}\n\n"
        f"Recent messages:\n{recent}\n\n"
        f"Evidence held by this chat:\n{_evidence_block(ctx.evidence)}\n\n"
        f"The owner's new message:\n{ctx.question}\n\n"
        f"What you have done so far this turn:\n{log_block(ctx.log)}{issues}\n\n{ending}"
    )
    result = await run_structured(engine, role="chat_orchestrator", job_id=run_id, prompt=prompt, model_cls=_Reply)
    step = result.value.step
    logger.info("orchestrator chose %s (%d step(s) left)", step.action, ctx.steps_left)
    return RunResult(value=step, cost_usd=result.cost_usd, fetched_urls=result.fetched_urls)

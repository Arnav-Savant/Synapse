"""Answer verifier: checks a draft answer against the evidence it cites."""

import logging
from typing import Literal

from pydantic import BaseModel, Field, model_validator

from app.agents.chat_orchestrator import EvidenceView
from app.agents.prompt_parts import UNTRUSTED_NOTES
from app.agents.runner import RunResult, run_structured
from app.engines.base import AgentEngine

logger = logging.getLogger(__name__)


class Verdict(BaseModel):
    verdict: Literal["pass", "revise"]
    issues: list[str] = Field(description="each problem, naming the claim; empty on pass")

    @model_validator(mode="after")
    def _revise_has_issues(self) -> "Verdict":
        if self.verdict == "revise" and not self.issues:
            raise ValueError("a `revise` verdict must list at least one issue")
        return self


async def verify_answer(
    engine: AgentEngine, *, run_id: str, question: str, answer_text: str, evidence: list[EvidenceView]
) -> RunResult[Verdict]:
    held = "\n\n".join(
        f"[E{e.ref}] {e.title} ({e.domain})" + (f" § {e.heading}" if e.heading else "") + f":\n{e.excerpt or '(not shown)'}"
        for e in evidence
    ) or "(no evidence)"
    prompt = (
        "You verify a draft answer in a study chat before the owner sees it. Check three things:\n"
        "1. Each claim drawn from the notes is supported by the excerpt it cites with [E#]. A claim with a citation that "
        "does not support it is an issue; so is a claim that overstates its excerpt.\n"
        "2. Material that is not from the notes is labelled as general knowledge, not presented as if the notes said it.\n"
        "3. The question is fully answered; what the notes do not cover is listed as a gap rather than glossed over.\n"
        "Return `pass` only if all three hold. Otherwise return `revise` with specific issues, each naming the claim.\n"
        f"{UNTRUSTED_NOTES}\n\n"
        f"Question:\n{question}\n\nDraft answer:\n{answer_text}\n\nEvidence it may cite:\n{held}"
    )
    result = await run_structured(engine, role="answer_verifier", job_id=run_id, prompt=prompt, model_cls=Verdict)
    logger.info("verifier verdict: %s (%d issue(s))", result.value.verdict, len(result.value.issues))
    return result

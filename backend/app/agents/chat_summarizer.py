"""Chat summarizer: folds older messages into the chat's running summary."""

import logging

from pydantic import BaseModel, Field

from app.agents.runner import RunResult, run_structured
from app.engines.base import AgentEngine

logger = logging.getLogger(__name__)


class Summary(BaseModel):
    summary: str = Field(min_length=1, description="under 400 words")


async def summarize_chat(
    engine: AgentEngine, *, run_id: str, previous_summary: str, messages: list[tuple[str, str]]
) -> RunResult[str]:
    text = "\n".join(f"{role}: {body}" for role, body in messages)
    prompt = (
        "You keep the running summary of a study chat so that older messages can be dropped. Fold the new messages into "
        "the previous summary. Keep the topics covered, the conclusions reached and the open threads (questions asked "
        "but not settled), in under 400 words. Write plain prose or short bullets, nothing else.\n\n"
        f"Previous summary:\n{previous_summary or '(none)'}\n\nNew messages:\n{text}"
    )
    result = await run_structured(engine, role="chat_summarizer", job_id=run_id, prompt=prompt, model_cls=Summary)
    logger.info("chat summary refreshed from %d message(s)", len(messages))
    return RunResult(value=result.value.summary, cost_usd=result.cost_usd, fetched_urls=result.fetched_urls)

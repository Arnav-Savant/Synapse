"""Runs one agent role and returns schema-validated output (Retry A, spec §8).

The caller builds the task prompt; this module appends the JSON-schema
instruction, parses the reply with `structured_output`, validates it against
the pydantic model and, on a bad shape, re-asks with the error attached (at
most `max_shape_retries` times). Engine failures (timeouts, crashes, rate
limits) are *not* retried here: they surface as `AgentEngineError` for
Temporal's infrastructure retry. Costs of every attempt are summed.
"""

import json
import logging
from dataclasses import dataclass
from typing import Generic, TypeVar

from pydantic import BaseModel, ValidationError

from app.agents.structured_output import extract_json_object
from app.engines.base import AgentEngine, AgentEngineError, EngineInvocation

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

_MAX_ECHO_CHARS = 8000  # how much of a rejected reply is shown back to the agent


class AgentOutputError(RuntimeError):
    """The agent never produced output matching its schema, even after re-asks.
    `cost_usd` is what the failed attempts cost, so callers can still record it."""

    def __init__(self, message: str, cost_usd: float = 0.0) -> None:
        super().__init__(message)
        self.cost_usd = cost_usd


@dataclass(frozen=True)
class RunResult(Generic[T]):
    value: T
    cost_usd: float
    fetched_urls: tuple[str, ...] | None


def _with_schema_instructions(prompt: str, model_cls: type[BaseModel]) -> str:
    schema = json.dumps(model_cls.model_json_schema(), separators=(",", ":"))
    return (
        f"{prompt}\n\n"
        "Reply with exactly one JSON object and nothing else: no prose before or after it, no code fence.\n"
        f"It must validate against this JSON Schema:\n{schema}"
    )


def _short(error: Exception) -> str:
    """One readable line: schema problems as 'field: what is wrong', without pydantic's input dump or docs link."""
    if isinstance(error, ValidationError):
        parts = [
            (f"{'.'.join(str(p) for p in e['loc'])}: " if e["loc"] else "") + e["msg"].removeprefix("Value error, ")
            for e in error.errors()
        ]
        return "; ".join(parts)[:600]
    return " ".join(str(error).split())[:600]


async def run_structured(
    engine: AgentEngine,
    *,
    role: str,
    job_id: str,
    prompt: str,
    model_cls: type[T],
    tools: tuple[str, ...] = (),
    max_shape_retries: int = 2,
    timeout_seconds: int = 300,
) -> RunResult[T]:
    base_prompt = _with_schema_instructions(prompt, model_cls)
    attempt_prompt = base_prompt
    total_cost = 0.0
    fetched: list[str] | None = []
    last_error: Exception | None = None

    for attempt in range(1, max_shape_retries + 2):
        result = await engine.invoke(
            EngineInvocation(
                agent_role=role, job_id=job_id, prompt=attempt_prompt, tools=tools, timeout_seconds=timeout_seconds
            )
        )
        total_cost += result.cost_usd or 0.0
        if result.fetched_urls is None:
            fetched = None
        elif fetched is not None:
            fetched.extend(u for u in result.fetched_urls if u not in fetched)
        if result.is_error:
            raise AgentEngineError(f"agent {role} reported an error: {result.result_text[:300]}")

        try:
            data = extract_json_object(result.result_text, (), AgentOutputError)
            value = model_cls.model_validate(data)
        except (AgentOutputError, ValidationError) as exc:
            last_error = exc
            logger.warning(
                "agent %s (job %s): reply had the wrong shape (attempt %d/%d): %s",
                role, job_id[:8], attempt, max_shape_retries + 1, _short(exc),
            )
            previous = result.result_text.strip()
            attempt_prompt = (
                f"{base_prompt}\n\nYour previous reply could not be used: {_short(exc)}\n"
                + (f"This is that reply:\n<<<\n{previous[:_MAX_ECHO_CHARS]}\n>>>\n" if previous else "")
                + "Reply again with only the corrected JSON object."
            )
            continue
        return RunResult(value=value, cost_usd=total_cost, fetched_urls=tuple(fetched) if fetched is not None else None)

    logger.error("agent %s (job %s): gave up after %d attempts, output never matched its schema", role, job_id[:8], max_shape_retries + 1)
    raise AgentOutputError(
        f"agent {role} did not return valid output after {max_shape_retries + 1} attempts: {_short(last_error)}",
        cost_usd=total_cost,
    )

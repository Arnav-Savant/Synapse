from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

DEFAULT_TIMEOUT_SECONDS = 300


class AgentEngineError(RuntimeError):
    """An engine invocation failed to run or produced an unusable result."""


@dataclass(frozen=True)
class EngineInvocation:
    agent_role: str                       # AgentConfig.agent_role PK — resolves model/effort
    job_id: str                           # for log lines only; the engine never uses it to scope anything
    prompt: str                           # fully-built prompt, built by the caller
    tools: tuple[str, ...] = ()           # built-in tools this call may use (e.g. WebSearch); empty = none
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class EngineResult:
    is_error: bool
    result_text: str
    cost_usd: float | None
    # URLs the session actually retrieved (WebFetch targets and WebSearch hits).
    # () when no web tool was available; None when it could not be determined.
    fetched_urls: tuple[str, ...] | None = None
    raw_metadata: dict = field(default_factory=dict)  # engine-specific passthrough, kept opaque


@runtime_checkable
class AgentEngine(Protocol):
    async def invoke(self, invocation: EngineInvocation) -> EngineResult: ...

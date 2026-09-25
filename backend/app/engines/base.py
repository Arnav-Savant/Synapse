from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable

DEFAULT_TIMEOUT_SECONDS = 300


class AgentEngineError(RuntimeError):
    """An engine invocation failed to run or produced an unusable result."""


@dataclass(frozen=True)
class EngineInvocation:
    agent_role: str                       # AgentConfig.agent_role PK — resolves engine/model/effort
    job_id: str                           # passed through for job-scoping (e.g. the MCP server subprocess)
    prompt: str                           # fully-built prompt (base contract + any critique delta) —
                                           # built by the caller (agents/orchestrator, a later phase), not the engine
    tool_names: tuple[str, ...] = ()      # domain tool names this call may use — caller-supplied, not
                                           # derived by the engine, so the engine stays reusable for
                                           # roles that don't have an MCP tool registry entry yet
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS


@dataclass(frozen=True)
class EngineResult:
    is_error: bool
    result_text: str
    cost_usd: float | None
    raw_metadata: dict = field(default_factory=dict)  # engine-specific passthrough — kept opaque
                                                        # rather than growing shared fields the two
                                                        # implementations don't actually share


@runtime_checkable
class AgentEngine(Protocol):
    async def invoke(self, invocation: EngineInvocation) -> EngineResult: ...

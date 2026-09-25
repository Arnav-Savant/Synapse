from app.engines.base import AgentEngineError, EngineInvocation, EngineResult


class LiteLLMNotConfiguredError(AgentEngineError):
    """LiteLLM support is scaffolded but not wired to a live provider yet."""


class LiteLLMEngine:
    """Scaffold only — no litellm package dependency, no live call. Always
    raises until a real provider/key is configured in a later phase."""

    async def invoke(self, invocation: EngineInvocation) -> EngineResult:
        raise LiteLLMNotConfiguredError(
            f"no LiteLLM provider configured for role {invocation.agent_role!r} — "
            "LiteLLM support is scaffolded but not implemented yet"
        )

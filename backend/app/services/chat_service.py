"""Chat orchestration: builds the chat prompt and invokes `ClaudeCodeEngine`
directly (the only engine chat has today — read-only, no API key required).

Phase 7 is expected to add a second (LiteLLM) engine and extend `ask()` to
pick between them based on the active `AgentConfig.engine` setting for the
`chat` role, without `api/chat.py` changing at all — `ClaudeCodeEngine`
already resolves model/effort per-call from that same row
(`engines/claude_code_engine.py`), and raises if it's configured for a
different engine, so this function's shape doesn't need to change to add
that branch later.
"""

from uuid import uuid4

from app.agents import chat_agent
from app.engines.base import EngineInvocation
from app.engines.claude_code_engine import ClaudeCodeEngine, ClaudeCodeEngineError
from app.mcp_server.server import AgentRole, TOOL_REGISTRY


async def ask(session_factory, message: str, concept_id: str | None = None) -> str:
    prompt = chat_agent.build_prompt(message, concept_id)
    engine = ClaudeCodeEngine(session_factory)
    result = await engine.invoke(
        EngineInvocation(
            agent_role=AgentRole.CHAT.value,
            # Chat isn't a job — no Job row, no job_rounds trace entry — this
            # is a synthetic per-request id, just satisfying EngineInvocation's
            # required field and giving any job-scoped read something stable
            # to key off, though Chat has no write tools so this mostly
            # doesn't matter.
            job_id=f"chat-{uuid4()}",
            prompt=prompt,
            tool_names=TOOL_REGISTRY[AgentRole.CHAT],
        )
    )
    # Same caller-checks-is_error convention as `claude_runner/naming.py`:
    # the engine surfaces is_error rather than raising on it itself.
    if result.is_error:
        raise ClaudeCodeEngineError(result.result_text or "claude reported an error")
    return result.result_text

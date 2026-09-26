import pytest

from app.engines.base import EngineResult
from app.engines.claude_code_engine import ClaudeCodeEngine, ClaudeCodeEngineError
from app.mcp_server.server import AgentRole, TOOL_REGISTRY
from app.services import chat_service


@pytest.mark.asyncio
async def test_ask_invokes_claude_code_engine_with_chat_tool_scope_and_returns_result_text(monkeypatch):
    captured = {}

    async def fake_invoke(self, invocation):
        captured["invocation"] = invocation
        return EngineResult(is_error=False, result_text="the answer", cost_usd=0.01)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    reply = await chat_service.ask(lambda: None, "What is prompt injection?", concept_id="prompt-injection")

    assert reply == "the answer"
    invocation = captured["invocation"]
    assert invocation.agent_role == AgentRole.CHAT.value
    assert invocation.tool_names == TOOL_REGISTRY[AgentRole.CHAT]
    assert "What is prompt injection?" in invocation.prompt
    assert "prompt-injection" in invocation.prompt
    assert invocation.job_id.startswith("chat-")


@pytest.mark.asyncio
async def test_ask_generates_a_fresh_synthetic_job_id_per_call(monkeypatch):
    job_ids = []

    async def fake_invoke(self, invocation):
        job_ids.append(invocation.job_id)
        return EngineResult(is_error=False, result_text="ok", cost_usd=None)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    await chat_service.ask(lambda: None, "hello")
    await chat_service.ask(lambda: None, "hello again")

    assert len(set(job_ids)) == 2


@pytest.mark.asyncio
async def test_ask_without_concept_id_still_invokes(monkeypatch):
    async def fake_invoke(self, invocation):
        return EngineResult(is_error=False, result_text="ok", cost_usd=None)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    reply = await chat_service.ask(lambda: None, "hello")

    assert reply == "ok"


@pytest.mark.asyncio
async def test_ask_propagates_engine_errors(monkeypatch):
    async def fake_invoke(self, invocation):
        raise ClaudeCodeEngineError("claude failed")

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    with pytest.raises(ClaudeCodeEngineError):
        await chat_service.ask(lambda: None, "hello")

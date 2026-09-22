import asyncio

import pytest

from app.claude_runner import chat_engine, runner
from app.claude_runner.runner import ClaudeRunResult


def test_respond_invokes_runner_with_read_only_tools(tmp_path, monkeypatch):
    captured = {}

    async def fake_run_claude(repo_path, prompt, *, tools=runner.READ_WRITE_TOOLS, **kwargs):
        captured["repo_path"] = repo_path
        captured["prompt"] = prompt
        captured["tools"] = tools
        return ClaudeRunResult(
            is_error=False,
            result_text="the answer",
            session_id="abc",
            total_cost_usd=0.01,
            permission_denials=[],
        )

    monkeypatch.setattr(runner, "run_claude", fake_run_claude)

    reply = asyncio.run(chat_engine.respond(tmp_path, "What is prompt injection?", None))

    assert reply == "the answer"
    assert captured["tools"] == runner.READ_ONLY_TOOLS
    assert "Write" not in captured["tools"]
    assert "Edit" not in captured["tools"]
    assert "What is prompt injection?" in captured["prompt"]


def test_respond_includes_concept_context_in_prompt(tmp_path, monkeypatch):
    captured = {}

    async def fake_run_claude(repo_path, prompt, **kwargs):
        captured["prompt"] = prompt
        return ClaudeRunResult(
            is_error=False, result_text="ok", session_id=None, total_cost_usd=None, permission_denials=[]
        )

    monkeypatch.setattr(runner, "run_claude", fake_run_claude)

    asyncio.run(chat_engine.respond(tmp_path, "tell me more", "prompt-injection"))

    assert "prompt-injection" in captured["prompt"]


def test_respond_raises_chat_engine_error_when_claude_reports_error(tmp_path, monkeypatch):
    async def fake_run_claude(repo_path, prompt, **kwargs):
        return ClaudeRunResult(
            is_error=True, result_text="something went wrong", session_id=None, total_cost_usd=None, permission_denials=[]
        )

    monkeypatch.setattr(runner, "run_claude", fake_run_claude)

    with pytest.raises(chat_engine.ChatEngineError):
        asyncio.run(chat_engine.respond(tmp_path, "hello", None))

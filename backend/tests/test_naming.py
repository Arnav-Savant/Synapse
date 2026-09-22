import asyncio

import pytest

from app.claude_runner import naming, runner
from app.claude_runner.runner import ClaudeRunResult


def _result(text: str, is_error: bool = False) -> ClaudeRunResult:
    return ClaudeRunResult(
        is_error=is_error, result_text=text, session_id=None, total_cost_usd=None, permission_denials=[]
    )


def test_suggest_source_location_parses_clean_json(tmp_path, monkeypatch):
    async def fake_run_claude(repo_path, prompt, **kwargs):
        return _result('{"category": "rag", "filename": "hybrid-search"}')

    monkeypatch.setattr(runner, "run_claude", fake_run_claude)

    category, filename = asyncio.run(naming.suggest_source_location(tmp_path, "some content"))

    assert category == "rag"
    assert filename == "hybrid-search"


def test_suggest_source_location_extracts_json_from_surrounding_text(tmp_path, monkeypatch):
    async def fake_run_claude(repo_path, prompt, **kwargs):
        return _result('Sure, here you go:\n```json\n{"category": "rag", "filename": "hybrid-search"}\n```')

    monkeypatch.setattr(runner, "run_claude", fake_run_claude)

    category, filename = asyncio.run(naming.suggest_source_location(tmp_path, "some content"))

    assert category == "rag"
    assert filename == "hybrid-search"


def test_suggest_source_location_uses_read_only_tools(tmp_path, monkeypatch):
    captured = {}

    async def fake_run_claude(repo_path, prompt, *, tools=runner.READ_WRITE_TOOLS, **kwargs):
        captured["tools"] = tools
        return _result('{"category": "x", "filename": "y"}')

    monkeypatch.setattr(runner, "run_claude", fake_run_claude)

    asyncio.run(naming.suggest_source_location(tmp_path, "content"))

    assert captured["tools"] == runner.READ_ONLY_TOOLS


def test_suggest_source_location_includes_topic_hint_in_prompt(tmp_path, monkeypatch):
    captured = {}

    async def fake_run_claude(repo_path, prompt, **kwargs):
        captured["prompt"] = prompt
        return _result('{"category": "x", "filename": "y"}')

    monkeypatch.setattr(runner, "run_claude", fake_run_claude)

    asyncio.run(naming.suggest_source_location(tmp_path, "content", topic_hint="retrieval augmented generation"))

    assert "retrieval augmented generation" in captured["prompt"]


def test_suggest_source_location_raises_on_claude_error(tmp_path, monkeypatch):
    async def fake_run_claude(repo_path, prompt, **kwargs):
        return _result("boom", is_error=True)

    monkeypatch.setattr(runner, "run_claude", fake_run_claude)

    with pytest.raises(naming.NamingError):
        asyncio.run(naming.suggest_source_location(tmp_path, "content"))


def test_suggest_source_location_raises_on_malformed_json(tmp_path, monkeypatch):
    async def fake_run_claude(repo_path, prompt, **kwargs):
        return _result("not json at all")

    monkeypatch.setattr(runner, "run_claude", fake_run_claude)

    with pytest.raises(naming.NamingError):
        asyncio.run(naming.suggest_source_location(tmp_path, "content"))


def test_suggest_source_location_raises_on_empty_values(tmp_path, monkeypatch):
    async def fake_run_claude(repo_path, prompt, **kwargs):
        return _result('{"category": "", "filename": "y"}')

    monkeypatch.setattr(runner, "run_claude", fake_run_claude)

    with pytest.raises(naming.NamingError):
        asyncio.run(naming.suggest_source_location(tmp_path, "content"))

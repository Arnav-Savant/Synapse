import asyncio
import json

import pytest

from app.claude_runner import runner


class FakeProcess:
    def __init__(self, stdout: bytes, stderr: bytes, returncode: int):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode

    async def communicate(self):
        return self._stdout, self._stderr

    def kill(self):
        pass

    async def wait(self):
        return self.returncode


class SlowProcess(FakeProcess):
    async def communicate(self):
        await asyncio.sleep(1)
        return self._stdout, self._stderr


def _success_payload(**overrides):
    payload = {
        "is_error": False,
        "result": "did the thing",
        "session_id": "abc123",
        "total_cost_usd": 0.05,
        "permission_denials": [],
    }
    payload.update(overrides)
    return payload


def test_run_claude_parses_successful_output(tmp_path, monkeypatch):
    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess(json.dumps(_success_payload()).encode(), b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    result = asyncio.run(runner.run_claude(tmp_path, "do something"))

    assert result.is_error is False
    assert result.result_text == "did the thing"
    assert result.session_id == "abc123"
    assert result.total_cost_usd == 0.05


def test_run_claude_raises_on_nonzero_exit(tmp_path, monkeypatch):
    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess(b"", b"boom", 1)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    with pytest.raises(runner.ClaudeRunnerError):
        asyncio.run(runner.run_claude(tmp_path, "do something"))


def test_run_claude_raises_on_invalid_json(tmp_path, monkeypatch):
    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess(b"not json", b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    with pytest.raises(runner.ClaudeRunnerError):
        asyncio.run(runner.run_claude(tmp_path, "do something"))


def test_run_claude_raises_on_timeout(tmp_path, monkeypatch):
    async def fake_create_subprocess_exec(*args, **kwargs):
        return SlowProcess(b"{}", b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    with pytest.raises(runner.ClaudeRunnerError):
        asyncio.run(runner.run_claude(tmp_path, "do something", timeout_seconds=0.05))


def test_run_claude_passes_expected_flags_and_cwd(tmp_path, monkeypatch):
    captured = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        captured["cwd"] = kwargs.get("cwd")
        return FakeProcess(json.dumps(_success_payload()).encode(), b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    asyncio.run(runner.run_claude(tmp_path, "hello"))

    args = captured["args"]
    assert args[0] == "claude"
    assert "--restricted" in args
    assert "--add-dir" in args
    assert str(tmp_path) in args
    assert "--permission-mode" in args
    assert "acceptEdits" in args
    assert captured["cwd"] == tmp_path


def test_run_claude_read_only_tools_excludes_write_and_edit(tmp_path, monkeypatch):
    captured = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        return FakeProcess(json.dumps(_success_payload()).encode(), b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    asyncio.run(runner.run_claude(tmp_path, "hello", tools=runner.READ_ONLY_TOOLS))

    tools_index = captured["args"].index("--tools") + 1
    tools_value = captured["args"][tools_index]
    assert "Write" not in tools_value
    assert "Edit" not in tools_value

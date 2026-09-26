import asyncio
import contextlib
import json
import sys
from pathlib import Path

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AgentConfig
from app.engines.base import EngineInvocation
from app.engines.claude_code_engine import (
    _ENTRYPOINT_PATH,
    ClaudeCodeEngine,
    ClaudeCodeEngineError,
)


class FakeProcess:
    def __init__(self, stdout: bytes, stderr: bytes, returncode: int):
        self._stdout = stdout
        self._stderr = stderr
        self.returncode = returncode
        self.killed = False

    async def communicate(self):
        return self._stdout, self._stderr

    def kill(self):
        self.killed = True

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


@pytest.fixture
def session_factory(db_session: AsyncSession):
    @contextlib.asynccontextmanager
    async def factory():
        yield db_session

    return factory


async def _seed(db_session: AsyncSession, **overrides) -> None:
    fields = {
        "agent_role": "text_agent",
        "engine": "claude_code",
        "provider": None,
        "model": "claude-sonnet-5",
        "effort": "medium",
        "env_key_name": None,
    }
    fields.update(overrides)
    db_session.add(AgentConfig(**fields))
    await db_session.flush()


@pytest.mark.asyncio
async def test_invoke_success_maps_result_and_flags(db_session, session_factory, monkeypatch):
    await _seed(db_session, agent_role="text_agent", model="claude-sonnet-5", effort="medium")

    captured = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        return FakeProcess(json.dumps(_success_payload()).encode(), b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    invocation = EngineInvocation(agent_role="text_agent", job_id="job-1", prompt="do the thing")
    engine = ClaudeCodeEngine(session_factory)

    result = await engine.invoke(invocation)

    args = captured["args"]
    assert args[0] == "claude"
    assert "--model" in args
    assert args[args.index("--model") + 1] == "claude-sonnet-5"
    assert "--effort" in args
    assert args[args.index("--effort") + 1] == "medium"

    assert result.is_error is False
    assert result.result_text == "did the thing"
    assert result.cost_usd == 0.05
    assert result.raw_metadata["session_id"] == "abc123"
    assert result.raw_metadata["permission_denials"] == []


@pytest.mark.asyncio
async def test_invoke_with_tool_names_builds_mcp_config_and_allowed_tools(
    db_session, session_factory, monkeypatch
):
    await _seed(db_session, agent_role="text_agent")

    captured = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        mcp_config_path = Path(args[args.index("--mcp-config") + 1])
        captured["mcp_config_path"] = mcp_config_path
        captured["mcp_config_content"] = json.loads(mcp_config_path.read_text())
        return FakeProcess(json.dumps(_success_payload()).encode(), b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    invocation = EngineInvocation(
        agent_role="text_agent",
        job_id="job-42",
        prompt="do the thing",
        tool_names=("search_concepts", "get_concept"),
    )
    engine = ClaudeCodeEngine(session_factory)

    await engine.invoke(invocation)

    args = captured["args"]
    assert "--mcp-config" in args
    assert "--strict-mcp-config" in args
    assert "--allowedTools" in args
    allowed_index = args.index("--allowedTools")
    assert args[allowed_index + 1 : allowed_index + 3] == (
        "mcp__synapse__search_concepts",
        "mcp__synapse__get_concept",
    )

    config_content = captured["mcp_config_content"]
    server_config = config_content["mcpServers"]["synapse"]
    assert server_config["command"] == sys.executable
    assert server_config["args"] == [
        str(_ENTRYPOINT_PATH),
        "--role",
        "text_agent",
        "--job-id",
        "job-42",
    ]
    assert not captured["mcp_config_path"].exists()


@pytest.mark.asyncio
async def test_invoke_without_tool_names_omits_mcp_flags(db_session, session_factory, monkeypatch):
    await _seed(db_session, agent_role="text_agent")

    captured = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        return FakeProcess(json.dumps(_success_payload()).encode(), b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    invocation = EngineInvocation(agent_role="text_agent", job_id="job-1", prompt="do the thing")
    engine = ClaudeCodeEngine(session_factory)

    await engine.invoke(invocation)

    args = captured["args"]
    assert "--mcp-config" not in args
    assert "--strict-mcp-config" not in args
    assert "--allowedTools" not in args


@pytest.mark.asyncio
async def test_invoke_wrong_engine_raises_without_spawning_subprocess(
    db_session, session_factory, monkeypatch
):
    await _seed(db_session, agent_role="chat", engine="litellm", model="gpt-5", effort="high")

    spawned = False

    async def fake_create_subprocess_exec(*args, **kwargs):
        nonlocal spawned
        spawned = True
        return FakeProcess(b"{}", b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    invocation = EngineInvocation(agent_role="chat", job_id="job-1", prompt="do the thing")
    engine = ClaudeCodeEngine(session_factory)

    with pytest.raises(ClaudeCodeEngineError):
        await engine.invoke(invocation)

    assert spawned is False


@pytest.mark.asyncio
async def test_invoke_timeout_raises_and_kills_process(db_session, session_factory, monkeypatch):
    await _seed(db_session, agent_role="text_agent")

    processes = []

    async def fake_create_subprocess_exec(*args, **kwargs):
        process = SlowProcess(b"{}", b"", 0)
        processes.append(process)
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    invocation = EngineInvocation(
        agent_role="text_agent", job_id="job-1", prompt="do the thing", timeout_seconds=0.05
    )
    engine = ClaudeCodeEngine(session_factory)

    with pytest.raises(ClaudeCodeEngineError):
        await engine.invoke(invocation)

    assert processes[0].killed is True


@pytest.mark.asyncio
async def test_invoke_nonzero_exit_raises(db_session, session_factory, monkeypatch):
    await _seed(db_session, agent_role="text_agent")

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess(b"", b"boom", 1)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    invocation = EngineInvocation(agent_role="text_agent", job_id="job-1", prompt="do the thing")
    engine = ClaudeCodeEngine(session_factory)

    with pytest.raises(ClaudeCodeEngineError):
        await engine.invoke(invocation)


@pytest.mark.asyncio
async def test_invoke_invalid_json_raises(db_session, session_factory, monkeypatch):
    await _seed(db_session, agent_role="text_agent")

    async def fake_create_subprocess_exec(*args, **kwargs):
        return FakeProcess(b"not json", b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    invocation = EngineInvocation(agent_role="text_agent", job_id="job-1", prompt="do the thing")
    engine = ClaudeCodeEngine(session_factory)

    with pytest.raises(ClaudeCodeEngineError):
        await engine.invoke(invocation)


@pytest.mark.asyncio
async def test_mcp_config_file_deleted_after_successful_call(db_session, session_factory, monkeypatch):
    await _seed(db_session, agent_role="text_agent")

    captured = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["mcp_config_path"] = Path(args[args.index("--mcp-config") + 1])
        return FakeProcess(json.dumps(_success_payload()).encode(), b"", 0)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    invocation = EngineInvocation(
        agent_role="text_agent", job_id="job-1", prompt="do the thing", tool_names=("search_concepts",)
    )
    engine = ClaudeCodeEngine(session_factory)

    await engine.invoke(invocation)

    assert not captured["mcp_config_path"].exists()


@pytest.mark.asyncio
async def test_mcp_config_file_deleted_after_error_call(db_session, session_factory, monkeypatch):
    await _seed(db_session, agent_role="text_agent")

    captured = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["mcp_config_path"] = Path(args[args.index("--mcp-config") + 1])
        return FakeProcess(b"", b"boom", 1)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    invocation = EngineInvocation(
        agent_role="text_agent", job_id="job-1", prompt="do the thing", tool_names=("search_concepts",)
    )
    engine = ClaudeCodeEngine(session_factory)

    with pytest.raises(ClaudeCodeEngineError):
        await engine.invoke(invocation)

    assert not captured["mcp_config_path"].exists()

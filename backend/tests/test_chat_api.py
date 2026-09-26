"""Chat's route resolves its `AgentConfig` row from Postgres via
`ClaudeCodeEngine`, so these requests need a seeded `chat` row to exist,
unlike the old filesystem-only `chat_engine.py` this replaces. The
subprocess boundary (`asyncio.create_subprocess_exec`, inside
`engines/claude_code_engine.py`) is mocked, same as
`tests/test_claude_code_engine.py` — no real `claude` process is spawned.

Uses `httpx.AsyncClient(transport=ASGITransport(app))` rather than
`fastapi.testclient.TestClient`, matching `tests/test_knowledge_api.py`'s
proven pattern: `TestClient` dispatches each request through an AnyIO
blocking-portal thread with its own event loop, which fails outright
(`asyncpg`'s `RuntimeError: ... attached to a different loop`) once a real
`AsyncSession`/`asyncpg` connection bound to this test's own (session-scoped)
event loop is threaded through.

`api/chat.py` doesn't route its Postgres session through a FastAPI
`Depends(...)` (it builds `contextlib.asynccontextmanager(postgres_connection.get_session)`
inline and hands the factory to `ClaudeCodeEngine`), so there's nothing to
put in `app.dependency_overrides` — instead `postgres_connection.get_session`
itself is monkeypatched per-test to yield this test's `db_session`, and the
`chat` `AgentConfig` row is seeded directly against that same session via
`app.db.seed.seed_default_agent_configs` (mirroring `tests/db/test_seed.py`)
rather than relying on the real app `lifespan` to have run.
"""

import json
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.postgres_connection import postgres_connection
from app.db.seed import seed_default_agent_configs
from app.engines import claude_code_engine
from app.main import app


class _FakeProcess:
    def __init__(self, stdout: bytes, returncode: int = 0):
        self._stdout = stdout
        self.returncode = returncode

    async def communicate(self):
        return self._stdout, b""

    def kill(self) -> None:
        pass

    async def wait(self) -> int:
        return self.returncode


def _payload(**overrides):
    payload = {
        "is_error": False,
        "result": "did the thing",
        "session_id": "abc",
        "total_cost_usd": 0.01,
        "permission_denials": [],
    }
    payload.update(overrides)
    return payload


@pytest.fixture
async def client(db_session: AsyncSession, monkeypatch) -> AsyncIterator[AsyncClient]:
    await seed_default_agent_configs(db_session)

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    monkeypatch.setattr(postgres_connection, "get_session", _override_get_session)

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client


@pytest.mark.asyncio
async def test_chat_returns_relevant_answer(client: AsyncClient, monkeypatch):
    async def fake_create_subprocess_exec(*args, **kwargs):
        return _FakeProcess(
            json.dumps(_payload(result="Prompt injection is when untrusted input hijacks a model's instructions.")).encode()
        )

    monkeypatch.setattr(claude_code_engine.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    response = await client.post("/api/chat", json={"message": "What is prompt injection?"})

    assert response.status_code == 200
    assert "hijacks" in response.json()["reply"]


@pytest.mark.asyncio
async def test_chat_scopes_tools_to_the_chat_role_read_only_set(client: AsyncClient, monkeypatch):
    captured = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        return _FakeProcess(json.dumps(_payload()).encode())

    monkeypatch.setattr(claude_code_engine.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    response = await client.post("/api/chat", json={"message": "hello", "concept_id": "prompt-injection"})

    assert response.status_code == 200
    args = captured["args"]
    allowed_index = args.index("--allowedTools")
    allowed_tools = args[allowed_index + 1 : allowed_index + 4]
    assert set(allowed_tools) == {
        "mcp__synapse__search_concepts",
        "mcp__synapse__get_concept",
        "mcp__synapse__get_graph_neighborhood",
    }
    # No Write/Edit-capable tool is ever offered — chat can never mutate
    # the knowledge base.
    assert not any("update" in t or "create" in t or "remove" in t for t in allowed_tools)


@pytest.mark.asyncio
async def test_chat_passes_concept_id_into_the_prompt(client: AsyncClient, monkeypatch):
    captured = {}

    async def fake_create_subprocess_exec(*args, **kwargs):
        captured["args"] = args
        return _FakeProcess(json.dumps(_payload()).encode())

    monkeypatch.setattr(claude_code_engine.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    await client.post("/api/chat", json={"message": "tell me more", "concept_id": "prompt-injection"})

    prompt = captured["args"][2]
    assert "prompt-injection" in prompt


@pytest.mark.asyncio
async def test_chat_works_with_no_concept_id(client: AsyncClient, monkeypatch):
    async def fake_create_subprocess_exec(*args, **kwargs):
        return _FakeProcess(json.dumps(_payload()).encode())

    monkeypatch.setattr(claude_code_engine.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    response = await client.post("/api/chat", json={"message": "hello"})

    assert response.status_code == 200


@pytest.mark.asyncio
async def test_chat_engine_error_returns_502(client: AsyncClient, monkeypatch):
    async def fake_create_subprocess_exec(*args, **kwargs):
        return _FakeProcess(json.dumps(_payload(is_error=True, result="claude failed")).encode())

    monkeypatch.setattr(claude_code_engine.asyncio, "create_subprocess_exec", fake_create_subprocess_exec)

    response = await client.post("/api/chat", json={"message": "hello"})

    assert response.status_code == 502


@pytest.mark.asyncio
async def test_chat_rejects_missing_message(client: AsyncClient):
    response = await client.post("/api/chat", json={})

    assert response.status_code == 422

"""Sources API tests against the Postgres-backed `source_service`/
`naming_agent` (Phase 4 Tasks 11+16 cutover). The old filesystem-era tests
(`filename`, `git_repo_factory`, `runner.run_claude`, path-traversal-by-
category) no longer apply — `Source` rows have no filename/path to collide
on, and there's no filesystem category folder to escape.

Same `AsyncClient`+`ASGITransport` rationale as `tests/test_knowledge_api.py`
(`TestClient`'s blocking-portal thread runs a different event loop than the
session-scoped `db_session` fixture's connection, which fails outright
once a route dependency is overridden with it). Also overrides
`get_job_queue` with a fresh, unstarted `JobQueue()` — with no `lifespan`
run under `ASGITransport`, `app.state.job_queue` was never set, and the
route depends on it via `Depends(get_job_queue)`.
"""

from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.sources import get_kuzu_conn
from app.core.postgres_connection import postgres_connection
from app.db.kuzu_db import get_kuzu_connection
from app.engines.base import EngineResult
from app.engines.claude_code_engine import ClaudeCodeEngine
from app.jobs.queue import JobQueue, get_job_queue
from app.main import app


@pytest.fixture
def kuzu_conn(tmp_path, monkeypatch):
    """Same fixture shape as `tests/test_graph_repo.py`/`test_knowledge_api.py`."""
    from app.core.config import get_server_config

    monkeypatch.setattr(get_server_config(), "kuzu_db_path", tmp_path / "graph")
    conn = get_kuzu_connection(tmp_path / "graph")
    yield conn
    get_kuzu_connection.cache_clear()
    import shutil

    shutil.rmtree(tmp_path / "graph", ignore_errors=True)


@pytest.fixture
async def client(db_session: AsyncSession, kuzu_conn) -> AsyncIterator[AsyncClient]:
    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[postgres_connection.get_session] = _override_get_session
    app.dependency_overrides[get_kuzu_conn] = lambda: kuzu_conn
    app.dependency_overrides[get_job_queue] = lambda: JobQueue()  # unstarted — enqueue() just queues, never runs
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()


def _fake_naming_invoke(category: str):
    async def fake(self, invocation):
        return EngineResult(is_error=False, result_text=f'{{"category": "{category}"}}', cost_usd=None)

    return fake


@pytest.mark.asyncio
async def test_create_and_list_source(client: AsyncClient):
    response = await client.post("/api/sources", json={"category": "prompt-engineering", "content": "hello"})

    assert response.status_code == 201
    body = response.json()
    assert body["source"]["category"] == "prompt-engineering"
    assert body["source"]["content"] == "hello"
    assert body["job_id"]

    listing = await client.get("/api/sources")
    assert listing.status_code == 200
    assert len(listing.json()["sources"]) == 1


@pytest.mark.asyncio
async def test_create_source_with_explicit_category_skips_naming_call(client: AsyncClient, monkeypatch):
    called = False

    async def tracking_fake(self, invocation):
        nonlocal called
        called = True
        return EngineResult(is_error=False, result_text='{"category": "unused"}', cost_usd=None)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", tracking_fake)

    response = await client.post("/api/sources", json={"category": "prompt-engineering", "content": "hello"})

    assert response.status_code == 201
    assert called is False


@pytest.mark.asyncio
async def test_create_source_with_auto_naming(client: AsyncClient, monkeypatch):
    monkeypatch.setattr(ClaudeCodeEngine, "invoke", _fake_naming_invoke("rag"))

    response = await client.post("/api/sources", json={"content": "some raw pasted content about RAG"})

    assert response.status_code == 201
    source = response.json()["source"]
    assert source["category"] == "rag"
    assert source["content"] == "some raw pasted content about RAG"


@pytest.mark.asyncio
async def test_create_source_rejects_empty_content(client: AsyncClient):
    response = await client.post("/api/sources", json={"content": ""})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_get_source_content(client: AsyncClient):
    created = await client.post("/api/sources", json={"category": "prompt-engineering", "content": "hello world"})
    source_id = created.json()["source"]["id"]

    response = await client.get(f"/api/sources/{source_id}")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == source_id
    assert body["content"] == "hello world"
    assert body["category"] == "prompt-engineering"


@pytest.mark.asyncio
async def test_get_missing_source_returns_404(client: AsyncClient):
    response = await client.get("/api/sources/does-not-exist")

    assert response.status_code == 404

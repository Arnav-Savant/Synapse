import shutil
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.graph import get_kuzu_conn
from app.core.config import get_server_config
from app.db.kuzu_db import get_kuzu_connection
from app.main import app
from app.services import graph_service


@pytest.fixture
async def client(kuzu_conn) -> AsyncIterator[AsyncClient]:
    """Uses `httpx.AsyncClient(transport=ASGITransport(app))` rather than
    `fastapi.testclient.TestClient`, matching `test_knowledge_api.py`'s
    pattern: `TestClient` dispatches each request through an AnyIO
    blocking-portal thread with its own event loop, which fails outright
    (`asyncpg`'s `RuntimeError: ... attached to a different loop`, confirmed
    empirically) once a route dependency is overridden with a connection
    already bound to this test's own (session-scoped, per `pyproject.toml`)
    event loop. `AsyncClient` + `ASGITransport` calls the ASGI app in-process
    on the caller's current event loop instead, so the overridden
    `get_kuzu_conn` is always used from the loop it was created on. This
    also means lifespan never runs here (no migrations, no job queue) — fine
    since this route has no Postgres dependency at all."""
    app.dependency_overrides[get_kuzu_conn] = lambda: kuzu_conn
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()


@pytest.fixture
def kuzu_conn(tmp_path, monkeypatch):
    """Same fixture shape as `tests/test_graph_repo.py`."""
    monkeypatch.setattr(get_server_config(), "kuzu_db_path", tmp_path / "graph")
    conn = get_kuzu_connection(tmp_path / "graph")
    yield conn
    get_kuzu_connection.cache_clear()
    shutil.rmtree(tmp_path / "graph", ignore_errors=True)


@pytest.fixture(autouse=True)
def _reset_graph_cache():
    graph_service.invalidate()
    yield
    graph_service.invalidate()


def _create_node(conn, concept_id, title, category):
    conn.execute(
        "CREATE (:Concept {id: $id, title: $title, category: $category})",
        {"id": concept_id, "title": title, "category": category},
    )


def _create_edge(conn, source_id, target_id, rel_type, *, status="committed", job_id="job-1"):
    conn.execute(
        "MATCH (a:Concept {id: $source}), (b:Concept {id: $target}) "
        "CREATE (a)-[:RELATES_TO {type: $type, note: '', justification: 'j', "
        "confidence: 0.9, status: $status, job_id: $job_id, created_at: current_timestamp()}]->(b)",
        {"source": source_id, "target": target_id, "type": rel_type, "status": status, "job_id": job_id},
    )


@pytest.mark.asyncio
async def test_get_graph_returns_nodes_and_edges(client: AsyncClient, kuzu_conn):
    _create_node(kuzu_conn, "prompt-engineering", "Prompt Engineering", "cat")
    _create_node(kuzu_conn, "few-shot-prompting", "Few-Shot Prompting", "cat")
    _create_edge(kuzu_conn, "few-shot-prompting", "prompt-engineering", "related-to")

    response = await client.get("/api/graph")

    assert response.status_code == 200
    body = response.json()
    assert {n["id"] for n in body["nodes"]} == {"prompt-engineering", "few-shot-prompting"}
    assert len(body["edges"]) == 1
    assert body["edges"][0]["source_id"] == "few-shot-prompting"
    assert body["edges"][0]["target_id"] == "prompt-engineering"
    assert body["edges"][0]["type"] == "related-to"


@pytest.mark.asyncio
async def test_get_graph_excludes_pending_edges(client: AsyncClient, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    _create_edge(kuzu_conn, "a", "b", "related-to", status="pending")

    response = await client.get("/api/graph")

    assert response.status_code == 200
    assert response.json()["edges"] == []

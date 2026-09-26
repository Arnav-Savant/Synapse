"""Direct tests for the six `/internal/graph/*` routes (`app/api/internal_graph.py`)
— the loopback-HTTP surface `app.mcp_server.graph_backend.RemoteGraphBackend`
calls instead of opening its own `kuzu.Connection` from the MCP server
subprocess (Kùzu is single-process-exclusive; see that module's docstring).

Same fixture shape as `tests/test_graph_api.py`/`tests/test_graph_repo.py`:
a real, temp-path Kùzu connection, and `httpx.AsyncClient` +
`ASGITransport` against the real `app.main.app` (no lifespan — this file's
routes have no Postgres dependency at all, matching `test_graph_api.py`'s
precedent).
"""

import shutil
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient

from app.api.internal_graph import get_kuzu_conn
from app.core.config import get_server_config
from app.db.kuzu_db import get_kuzu_connection
from app.main import app
from app.repositories import graph_repo


@pytest.fixture
def kuzu_conn(tmp_path, monkeypatch):
    """Same fixture shape as `tests/test_graph_repo.py`."""
    monkeypatch.setattr(get_server_config(), "kuzu_db_path", tmp_path / "graph")
    conn = get_kuzu_connection(tmp_path / "graph")
    yield conn
    get_kuzu_connection.cache_clear()
    shutil.rmtree(tmp_path / "graph", ignore_errors=True)


@pytest.fixture
async def client(kuzu_conn) -> AsyncIterator[AsyncClient]:
    app.dependency_overrides[get_kuzu_conn] = lambda: kuzu_conn
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()


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


# --- get_graph_neighborhood --------------------------------------------------


async def test_get_graph_neighborhood_returns_nodes_and_edges(client: AsyncClient, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    _create_edge(kuzu_conn, "a", "b", "related-to")

    response = await client.get("/internal/graph/neighborhood/a", params={"depth": 1})

    assert response.status_code == 200
    body = response.json()
    assert body["center_id"] == "a"
    assert {n["id"] for n in body["nodes"]} == {"a", "b"}
    assert len(body["edges"]) == 1
    assert body["edges"][0] == {
        "source_id": "a", "target_id": "b", "type": "related-to", "note": "",
        "justification": "j", "confidence": 0.9, "status": "committed", "job_id": "job-1",
    }


async def test_get_graph_neighborhood_unknown_concept_returns_404_with_error_type(client: AsyncClient):
    response = await client.get("/internal/graph/neighborhood/ghost")

    assert response.status_code == 404
    assert response.json()["error"] == "ConceptNotFoundInGraphError"


async def test_get_graph_neighborhood_invalid_depth_returns_400(client: AsyncClient, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")

    response = await client.get("/internal/graph/neighborhood/a", params={"depth": 999})

    assert response.status_code == 400
    assert response.json()["error"] == "InvalidGraphInputError"


# --- search_relationships -----------------------------------------------------


async def test_search_relationships_returns_matches(client: AsyncClient, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    _create_edge(kuzu_conn, "a", "b", "related-to")

    response = await client.get("/internal/graph/relationships/a")

    assert response.status_code == 200
    relationships = response.json()["relationships"]
    assert len(relationships) == 1
    assert relationships[0]["source_id"] == "a"
    assert relationships[0]["target_id"] == "b"


# --- ensure_node --------------------------------------------------------------


async def test_ensure_node_creates_concept_node(client: AsyncClient, kuzu_conn):
    response = await client.post(
        "/internal/graph/nodes", json={"id": "a", "title": "A", "category": "cat"}
    )

    assert response.status_code == 204
    result = kuzu_conn.execute("MATCH (c:Concept {id: $id}) RETURN c.title, c.category", {"id": "a"})
    assert result.has_next()
    assert result.get_next() == ["A", "cat"]


# --- add_relationship -----------------------------------------------------------


async def test_add_relationship_creates_pending_edge(client: AsyncClient, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")

    response = await client.post(
        "/internal/graph/relationships",
        json={"source_id": "a", "target_id": "b", "type": "related-to", "justification": "j", "job_id": "job-1"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pending"
    assert body["job_id"] == "job-1"


async def test_add_relationship_dangling_target_returns_404_with_error_type(client: AsyncClient, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")

    response = await client.post(
        "/internal/graph/relationships",
        json={"source_id": "a", "target_id": "ghost", "type": "related-to", "justification": "j", "job_id": "job-1"},
    )

    assert response.status_code == 404
    assert response.json()["error"] == "ConceptNotFoundInGraphError"


async def test_add_relationship_cycle_returns_409_with_error_type(client: AsyncClient, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    _create_node(kuzu_conn, "c", "C", "cat")
    graph_repo.add_relationship(kuzu_conn, source_id="a", target_id="b", type="subtopic-of", justification="j", job_id="job-1")
    graph_repo.add_relationship(kuzu_conn, source_id="b", target_id="c", type="subtopic-of", justification="j", job_id="job-1")

    response = await client.post(
        "/internal/graph/relationships",
        json={"source_id": "c", "target_id": "a", "type": "subtopic-of", "justification": "j", "job_id": "job-1"},
    )

    assert response.status_code == 409
    assert response.json()["error"] == "CyclicRelationshipError"


async def test_add_relationship_duplicate_returns_409_with_error_type(client: AsyncClient, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    graph_repo.add_relationship(kuzu_conn, source_id="a", target_id="b", type="example-of", justification="j", job_id="job-1")

    response = await client.post(
        "/internal/graph/relationships",
        json={"source_id": "a", "target_id": "b", "type": "example-of", "justification": "j2", "job_id": "job-1"},
    )

    assert response.status_code == 409
    assert response.json()["error"] == "DuplicateRelationshipError"


async def test_add_relationship_symmetric_conflict_returns_409_with_error_type(client: AsyncClient, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    graph_repo.add_relationship(kuzu_conn, source_id="a", target_id="b", type="contrasts-with", justification="j", job_id="job-1")

    response = await client.post(
        "/internal/graph/relationships",
        json={"source_id": "b", "target_id": "a", "type": "contrasts-with", "justification": "j2", "job_id": "job-1"},
    )

    assert response.status_code == 409
    assert response.json()["error"] == "SymmetricRelationshipConflictError"


# --- update_relationship --------------------------------------------------------


async def test_update_relationship_applies_partial_update(client: AsyncClient, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    graph_repo.add_relationship(kuzu_conn, source_id="a", target_id="b", type="related-to", justification="j", job_id="job-1")

    response = await client.patch(
        "/internal/graph/relationships",
        json={"source_id": "a", "target_id": "b", "type": "related-to", "job_id": "job-1", "note": "updated"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["note"] == "updated"
    assert body["justification"] == "j"


async def test_update_relationship_not_found_returns_404_with_error_type(client: AsyncClient, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")

    response = await client.patch(
        "/internal/graph/relationships",
        json={"source_id": "a", "target_id": "b", "type": "related-to", "job_id": "job-1", "note": "x"},
    )

    assert response.status_code == 404
    assert response.json()["error"] == "RelationshipNotFoundError"


# --- remove_relationship --------------------------------------------------------


async def test_remove_relationship_deletes_edge(client: AsyncClient, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    graph_repo.add_relationship(kuzu_conn, source_id="a", target_id="b", type="related-to", justification="j", job_id="job-1")

    response = await client.request(
        "DELETE",
        "/internal/graph/relationships",
        json={"source_id": "a", "target_id": "b", "type": "related-to", "job_id": "job-1"},
    )

    assert response.status_code == 204
    remaining = graph_repo.search_relationships(kuzu_conn, "a", job_id="job-1")
    assert remaining == []


async def test_remove_relationship_not_found_returns_404_with_error_type(client: AsyncClient, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")

    response = await client.request(
        "DELETE",
        "/internal/graph/relationships",
        json={"source_id": "a", "target_id": "b", "type": "related-to", "job_id": "job-1"},
    )

    assert response.status_code == 404
    assert response.json()["error"] == "RelationshipNotFoundError"

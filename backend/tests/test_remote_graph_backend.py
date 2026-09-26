"""`RemoteGraphBackend` (`app/mcp_server/graph_backend.py`) against a real,
running instance of `app.main.app` — the one genuinely new code path
nothing else in this suite exercises: reconstructing `graph_repo`'s
dataclasses *and* its exact domain exception types from real HTTP
responses.

Uses a real `uvicorn.Server` on a loopback socket (`lifespan="off"`, no
Postgres/migrations involved — these six routes have no Postgres
dependency), rather than this suite's usual `httpx.AsyncClient` +
`ASGITransport` convention: `RemoteGraphBackend` makes genuine synchronous
`httpx.Client` calls (every tool builder that touches these six operations
is a plain, non-async function — see `mcp_server/server.py`), and
`httpx.ASGITransport` only implements the async transport interface, so it
cannot stand in for a sync client here.
"""

import shutil
import socket
import threading
import time
from collections.abc import Iterator

import pytest
import uvicorn

from app.api.internal_graph import get_kuzu_conn
from app.core.config import get_server_config
from app.db.kuzu_db import get_kuzu_connection
from app.main import app
from app.mcp_server.graph_backend import RemoteGraphBackend
from app.repositories import graph_repo


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


@pytest.fixture(scope="module")
def live_server_base_url() -> Iterator[str]:
    port = _free_port()
    config = uvicorn.Config(app, host="127.0.0.1", port=port, lifespan="off", log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.01)
    yield f"http://127.0.0.1:{port}"
    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def kuzu_conn(tmp_path, monkeypatch):
    """Same fixture shape as `tests/test_graph_repo.py`."""
    monkeypatch.setattr(get_server_config(), "kuzu_db_path", tmp_path / "graph")
    conn = get_kuzu_connection(tmp_path / "graph")
    yield conn
    get_kuzu_connection.cache_clear()
    shutil.rmtree(tmp_path / "graph", ignore_errors=True)


@pytest.fixture
def backend(live_server_base_url, kuzu_conn) -> Iterator[RemoteGraphBackend]:
    app.dependency_overrides[get_kuzu_conn] = lambda: kuzu_conn
    remote = RemoteGraphBackend(live_server_base_url)
    yield remote
    remote.close()
    app.dependency_overrides.clear()


def _create_node(conn, concept_id, title, category):
    conn.execute(
        "CREATE (:Concept {id: $id, title: $title, category: $category})",
        {"id": concept_id, "title": title, "category": category},
    )


# --- Happy-path reconstruction ------------------------------------------------


def test_get_graph_neighborhood_reconstructs_dataclass(backend, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    graph_repo.add_relationship(kuzu_conn, source_id="a", target_id="b", type="related-to", justification="j", job_id="job-1")

    result = backend.get_graph_neighborhood("a", depth=1, job_id="job-1")

    direct = graph_repo.get_graph_neighborhood(kuzu_conn, "a", depth=1, job_id="job-1")
    assert result.center_id == direct.center_id
    assert set(result.nodes) == set(direct.nodes)
    assert set(result.edges) == set(direct.edges)


def test_get_graph_neighborhood_committed_only_when_job_id_omitted(backend, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    graph_repo.add_relationship(kuzu_conn, source_id="a", target_id="b", type="related-to", justification="j", job_id="job-1")

    result = backend.get_graph_neighborhood("a", depth=1)

    assert result.edges == []


def test_search_relationships_reconstructs_dataclasses(backend, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    graph_repo.add_relationship(
        kuzu_conn, source_id="a", target_id="b", type="related-to", justification="j", note="n",
        confidence=0.7, job_id="job-1",
    )

    result = backend.search_relationships("a", job_id="job-1")

    direct = graph_repo.search_relationships(kuzu_conn, "a", job_id="job-1")
    assert set(result) == set(direct)


def test_ensure_node_upserts_via_real_request(backend, kuzu_conn):
    backend.ensure_node("a", "A", "cat")

    node_result = kuzu_conn.execute("MATCH (c:Concept {id: $id}) RETURN c.title, c.category", {"id": "a"})
    assert node_result.has_next()
    assert node_result.get_next() == ["A", "cat"]


def test_add_relationship_reconstructs_dataclass(backend, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")

    result = backend.add_relationship(
        source_id="a", target_id="b", type="related-to", justification="j", note="n", confidence=0.5, job_id="job-1"
    )

    assert result == graph_repo.RelationshipRecord(
        source_id="a", target_id="b", type="related-to", note="n", justification="j",
        confidence=0.5, status="pending", job_id="job-1",
    )


def test_update_relationship_reconstructs_dataclass(backend, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    graph_repo.add_relationship(kuzu_conn, source_id="a", target_id="b", type="related-to", justification="j", job_id="job-1")

    result = backend.update_relationship(source_id="a", target_id="b", type="related-to", job_id="job-1", note="updated")

    assert result.note == "updated"
    assert result.justification == "j"


def test_remove_relationship_deletes_via_real_request(backend, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    graph_repo.add_relationship(kuzu_conn, source_id="a", target_id="b", type="related-to", justification="j", job_id="job-1")

    backend.remove_relationship(source_id="a", target_id="b", type="related-to", job_id="job-1")

    assert graph_repo.search_relationships(kuzu_conn, "a", job_id="job-1") == []


# --- Exception reconstruction (one per domain exception type) ---------------


def test_concept_not_found_in_graph_error_reconstructed(backend):
    with pytest.raises(graph_repo.ConceptNotFoundInGraphError):
        backend.get_graph_neighborhood("ghost")


def test_invalid_graph_input_error_reconstructed(backend, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")

    with pytest.raises(graph_repo.InvalidGraphInputError):
        backend.get_graph_neighborhood("a", depth=999)


def test_cyclic_relationship_error_reconstructed(backend, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    _create_node(kuzu_conn, "c", "C", "cat")
    graph_repo.add_relationship(kuzu_conn, source_id="a", target_id="b", type="subtopic-of", justification="j", job_id="job-1")
    graph_repo.add_relationship(kuzu_conn, source_id="b", target_id="c", type="subtopic-of", justification="j", job_id="job-1")

    with pytest.raises(graph_repo.CyclicRelationshipError):
        backend.add_relationship(source_id="c", target_id="a", type="subtopic-of", justification="j", job_id="job-1")


def test_duplicate_relationship_error_reconstructed(backend, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    graph_repo.add_relationship(kuzu_conn, source_id="a", target_id="b", type="example-of", justification="j", job_id="job-1")

    with pytest.raises(graph_repo.DuplicateRelationshipError):
        backend.add_relationship(source_id="a", target_id="b", type="example-of", justification="j2", job_id="job-1")


def test_symmetric_relationship_conflict_error_reconstructed(backend, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    graph_repo.add_relationship(kuzu_conn, source_id="a", target_id="b", type="contrasts-with", justification="j", job_id="job-1")

    with pytest.raises(graph_repo.SymmetricRelationshipConflictError):
        backend.add_relationship(source_id="b", target_id="a", type="contrasts-with", justification="j2", job_id="job-1")


def test_relationship_not_found_error_reconstructed(backend, kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")

    with pytest.raises(graph_repo.RelationshipNotFoundError):
        backend.remove_relationship(source_id="a", target_id="b", type="related-to", job_id="job-1")

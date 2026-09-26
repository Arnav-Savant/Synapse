import shutil

import pytest

from app.core.config import get_server_config
from app.db.kuzu_db import get_kuzu_connection
from app.services import graph_service


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
    """The service cache is a single module-level entry now (one Kùzu
    database for the whole app), so it must be reset around every test —
    unlike the old per-repo-path dict, distinct tmp_paths no longer give
    tests cache isolation for free."""
    graph_service.invalidate()
    yield
    graph_service.invalidate()


def _create_node(conn, concept_id, title, category):
    conn.execute(
        "CREATE (:Concept {id: $id, title: $title, category: $category})",
        {"id": concept_id, "title": title, "category": category},
    )


def test_get_graph_reflects_kuzu_state(kuzu_conn):
    _create_node(kuzu_conn, "prompt-engineering", "Prompt Engineering", "cat")

    graph = graph_service.get_graph(kuzu_conn)

    assert {n.id for n in graph.nodes} == {"prompt-engineering"}


def test_get_graph_caches_until_invalidated(kuzu_conn):
    _create_node(kuzu_conn, "prompt-engineering", "Prompt Engineering", "cat")

    graph_service.get_graph(kuzu_conn)
    _create_node(kuzu_conn, "few-shot-prompting", "Few-Shot Prompting", "cat")

    # Not invalidated yet — should still reflect the cached (stale) state.
    stale_graph = graph_service.get_graph(kuzu_conn)
    assert {n.id for n in stale_graph.nodes} == {"prompt-engineering"}

    graph_service.invalidate()
    fresh_graph = graph_service.get_graph(kuzu_conn)
    assert {n.id for n in fresh_graph.nodes} == {"prompt-engineering", "few-shot-prompting"}

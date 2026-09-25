import shutil

import pytest

from app.core.config import get_server_config
from app.db.kuzu_db import get_kuzu_connection


@pytest.fixture
def kuzu_conn(tmp_path, monkeypatch):
    monkeypatch.setattr(get_server_config(), "kuzu_db_path", tmp_path / "graph")
    conn = get_kuzu_connection(tmp_path / "graph")
    yield conn
    shutil.rmtree(tmp_path / "graph", ignore_errors=True)


def test_node_and_edge_roundtrip(kuzu_conn):
    kuzu_conn.execute("CREATE (:Concept {id: 'c1', title: 'Backprop', category: 'nn'})")
    kuzu_conn.execute("CREATE (:Concept {id: 'c2', title: 'Gradient Descent', category: 'nn'})")
    kuzu_conn.execute(
        "MATCH (a:Concept {id: 'c1'}), (b:Concept {id: 'c2'}) "
        "CREATE (a)-[:RELATES_TO {type: 'related-to', note: '', justification: 'both covered in same source', "
        "confidence: 0.9, status: 'committed', job_id: 'job-1', created_at: timestamp('2026-01-01')}]->(b)"
    )
    result = kuzu_conn.execute(
        "MATCH (a:Concept {id: 'c1'})-[r:RELATES_TO]->(b:Concept) RETURN b.id, r.type"
    )
    row = result.get_next()
    assert row[0] == "c2"
    assert row[1] == "related-to"

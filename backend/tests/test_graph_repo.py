import shutil

import kuzu
import pytest

from app.core.config import get_server_config
from app.db.kuzu_db import get_kuzu_connection
from app.repositories.graph_repo import (
    ConceptNotFoundInGraphError,
    CyclicRelationshipError,
    DuplicateRelationshipError,
    InvalidGraphInputError,
    RelationshipNotFoundError,
    SymmetricRelationshipConflictError,
    add_relationship,
    ensure_node,
    get_graph_neighborhood,
    remove_relationship,
    search_relationships,
    update_relationship,
    would_create_cycle,
)


@pytest.fixture
def kuzu_conn(tmp_path, monkeypatch):
    monkeypatch.setattr(get_server_config(), "kuzu_db_path", tmp_path / "graph")
    conn = get_kuzu_connection(tmp_path / "graph")
    yield conn
    # get_kuzu_connection is @lru_cache'd keyed by path; each test uses a
    # distinct tmp_path so entries never collide but also never evict,
    # accumulating open kuzu.Database mmap reservations across a full test
    # run until the process exhausts address space. Clearing here (in
    # addition to the existing directory cleanup) drops the cached
    # Connection/Database so they can be garbage-collected per test.
    get_kuzu_connection.cache_clear()
    shutil.rmtree(tmp_path / "graph", ignore_errors=True)


def _create_node(conn, concept_id, title, category):
    conn.execute(
        "CREATE (:Concept {id: $id, title: $title, category: $category})",
        {"id": concept_id, "title": title, "category": category},
    )


def _create_edge(conn, source_id, target_id, rel_type, *, note="", justification="j",
                  confidence=0.9, status="committed", job_id="job-1"):
    conn.execute(
        "MATCH (a:Concept {id: $source}), (b:Concept {id: $target}) "
        "CREATE (a)-[:RELATES_TO {type: $type, note: $note, justification: $justification, "
        "confidence: $confidence, status: $status, job_id: $job_id, "
        "created_at: timestamp('2026-01-01')}]->(b)",
        {
            "source": source_id,
            "target": target_id,
            "type": rel_type,
            "note": note,
            "justification": justification,
            "confidence": confidence,
            "status": status,
            "job_id": job_id,
        },
    )


def _build_chain_fixture(conn):
    """a - b - c - d chain, plus an isolated node e, all connected via
    related-to/subtopic-of edges."""
    _create_node(conn, "a", "A", "cat")
    _create_node(conn, "b", "B", "cat")
    _create_node(conn, "c", "C", "cat")
    _create_node(conn, "d", "D", "cat")
    _create_node(conn, "e", "E", "cat")
    _create_edge(conn, "a", "b", "related-to")
    _create_edge(conn, "b", "c", "subtopic-of")
    _create_edge(conn, "c", "d", "related-to")


def test_ensure_node_is_idempotent(kuzu_conn):
    ensure_node(kuzu_conn, "c1", "Backprop", "nn")
    ensure_node(kuzu_conn, "c1", "Backprop", "nn")

    result = kuzu_conn.execute("MATCH (c:Concept {id: 'c1'}) RETURN COUNT(*)")
    assert result.get_next()[0] == 1


def test_ensure_node_updates_fields_on_match(kuzu_conn):
    ensure_node(kuzu_conn, "c1", "Old Title", "old-cat")
    ensure_node(kuzu_conn, "c1", "New Title", "new-cat")

    result = kuzu_conn.execute("MATCH (c:Concept {id: 'c1'}) RETURN c.title, c.category")
    row = result.get_next()
    assert row == ["New Title", "new-cat"]


def test_get_graph_neighborhood_depth_1(kuzu_conn):
    _build_chain_fixture(kuzu_conn)

    neighborhood = get_graph_neighborhood(kuzu_conn, "b", depth=1)

    assert neighborhood.center_id == "b"
    assert {n.id for n in neighborhood.nodes} == {"a", "b", "c"}
    assert {(e.source_id, e.target_id) for e in neighborhood.edges} == {("a", "b"), ("b", "c")}


def test_get_graph_neighborhood_depth_2(kuzu_conn):
    _build_chain_fixture(kuzu_conn)

    neighborhood = get_graph_neighborhood(kuzu_conn, "b", depth=2)

    assert {n.id for n in neighborhood.nodes} == {"a", "b", "c", "d"}
    assert {(e.source_id, e.target_id) for e in neighborhood.edges} == {
        ("a", "b"),
        ("b", "c"),
        ("c", "d"),
    }


def test_get_graph_neighborhood_edge_fields(kuzu_conn):
    _build_chain_fixture(kuzu_conn)

    neighborhood = get_graph_neighborhood(kuzu_conn, "b", depth=1)
    edge = next(e for e in neighborhood.edges if e.source_id == "a" and e.target_id == "b")

    assert edge.type == "related-to"
    assert edge.note == ""
    assert edge.justification == "j"
    assert edge.confidence == pytest.approx(0.9)
    assert edge.status == "committed"
    assert edge.job_id == "job-1"


def test_get_graph_neighborhood_unknown_concept_raises(kuzu_conn):
    _build_chain_fixture(kuzu_conn)

    with pytest.raises(ConceptNotFoundInGraphError):
        get_graph_neighborhood(kuzu_conn, "does-not-exist", depth=1)


def test_get_graph_neighborhood_depth_above_bound_raises(kuzu_conn):
    _build_chain_fixture(kuzu_conn)

    with pytest.raises(InvalidGraphInputError):
        get_graph_neighborhood(kuzu_conn, "b", depth=6)


def test_get_graph_neighborhood_negative_depth_raises(kuzu_conn):
    _build_chain_fixture(kuzu_conn)

    with pytest.raises(InvalidGraphInputError):
        get_graph_neighborhood(kuzu_conn, "b", depth=-1)


def test_search_relationships_both_directions(kuzu_conn):
    _build_chain_fixture(kuzu_conn)

    relationships = search_relationships(kuzu_conn, "b")

    pairs = {(r.source_id, r.target_id) for r in relationships}
    assert pairs == {("a", "b"), ("b", "c")}
    assert len(relationships) == 2


# --- add_relationship: Layer 1 rejection cases ---------------------------


def test_add_relationship_missing_target_raises(kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")

    with pytest.raises(ConceptNotFoundInGraphError):
        add_relationship(
            kuzu_conn, source_id="a", target_id="does-not-exist", type="related-to",
            justification="j", job_id="job-1",
        )


def test_add_relationship_missing_source_raises(kuzu_conn):
    _create_node(kuzu_conn, "b", "B", "cat")

    with pytest.raises(ConceptNotFoundInGraphError):
        add_relationship(
            kuzu_conn, source_id="does-not-exist", target_id="b", type="related-to",
            justification="j", job_id="job-1",
        )


def test_add_relationship_missing_both_raises(kuzu_conn):
    with pytest.raises(ConceptNotFoundInGraphError):
        add_relationship(
            kuzu_conn, source_id="ghost-1", target_id="ghost-2", type="related-to",
            justification="j", job_id="job-1",
        )


def test_add_relationship_self_loop_raises(kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")

    with pytest.raises(InvalidGraphInputError):
        add_relationship(
            kuzu_conn, source_id="a", target_id="a", type="related-to",
            justification="j", job_id="job-1",
        )


def test_add_relationship_unknown_type_raises(kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")

    with pytest.raises(InvalidGraphInputError):
        add_relationship(
            kuzu_conn, source_id="a", target_id="b", type="not-a-real-type",
            justification="j", job_id="job-1",
        )


def test_add_relationship_blank_justification_raises(kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")

    with pytest.raises(InvalidGraphInputError):
        add_relationship(
            kuzu_conn, source_id="a", target_id="b", type="related-to",
            justification="   ", job_id="job-1",
        )


# --- add_relationship: duplicate/conflict cases ---------------------------


def test_add_relationship_duplicate_exact_directional_raises(kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    add_relationship(
        kuzu_conn, source_id="a", target_id="b", type="example-of",
        justification="j", job_id="job-1",
    )

    with pytest.raises(DuplicateRelationshipError):
        add_relationship(
            kuzu_conn, source_id="a", target_id="b", type="example-of",
            justification="j2", job_id="job-1",
        )


def test_add_relationship_duplicate_pending_same_job_raises(kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    add_relationship(
        kuzu_conn, source_id="a", target_id="b", type="used-in",
        justification="j", job_id="job-a",
    )

    with pytest.raises(DuplicateRelationshipError):
        add_relationship(
            kuzu_conn, source_id="a", target_id="b", type="used-in",
            justification="j2", job_id="job-a",
        )


def test_add_relationship_duplicate_committed_across_jobs_raises(kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    _create_edge(kuzu_conn, "a", "b", "used-in", status="committed", job_id="job-a")

    with pytest.raises(DuplicateRelationshipError):
        add_relationship(
            kuzu_conn, source_id="a", target_id="b", type="used-in",
            justification="j2", job_id="job-b",
        )


def test_add_relationship_symmetric_same_direction_conflict_raises(kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    add_relationship(
        kuzu_conn, source_id="a", target_id="b", type="related-to",
        justification="j", job_id="job-1",
    )

    with pytest.raises(SymmetricRelationshipConflictError):
        add_relationship(
            kuzu_conn, source_id="a", target_id="b", type="related-to",
            justification="j2", job_id="job-1",
        )


def test_add_relationship_symmetric_reverse_direction_conflict_raises(kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    add_relationship(
        kuzu_conn, source_id="a", target_id="b", type="contrasts-with",
        justification="j", job_id="job-1",
    )

    with pytest.raises(SymmetricRelationshipConflictError):
        add_relationship(
            kuzu_conn, source_id="b", target_id="a", type="contrasts-with",
            justification="j2", job_id="job-1",
        )


# --- add_relationship: success cases --------------------------------------


@pytest.mark.parametrize(
    "edge_type",
    ["subtopic-of", "prerequisite-of", "example-of", "used-in", "contrasts-with", "related-to"],
)
def test_add_relationship_succeeds_for_each_taxonomy_type(kuzu_conn, edge_type):
    source_id = f"src-{edge_type}"
    target_id = f"tgt-{edge_type}"
    _create_node(kuzu_conn, source_id, "Source", "cat")
    _create_node(kuzu_conn, target_id, "Target", "cat")

    record = add_relationship(
        kuzu_conn, source_id=source_id, target_id=target_id, type=edge_type,
        justification="because reasons", note="a note", confidence=0.75, job_id="job-1",
    )

    assert record.source_id == source_id
    assert record.target_id == target_id
    assert record.type == edge_type
    assert record.justification == "because reasons"
    assert record.note == "a note"
    assert record.confidence == pytest.approx(0.75)
    assert record.status == "pending"
    assert record.job_id == "job-1"

    stored = [r for r in search_relationships(kuzu_conn, source_id) if r.type == edge_type]
    assert len(stored) == 1
    assert stored[0] == record


# --- would_create_cycle / cycle rejection ----------------------------------


def test_add_relationship_cycle_rejected(kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    _create_node(kuzu_conn, "c", "C", "cat")
    add_relationship(kuzu_conn, source_id="a", target_id="b", type="subtopic-of", justification="j", job_id="job-1")
    add_relationship(kuzu_conn, source_id="b", target_id="c", type="subtopic-of", justification="j", job_id="job-1")

    with pytest.raises(CyclicRelationshipError):
        add_relationship(
            kuzu_conn, source_id="c", target_id="a", type="subtopic-of",
            justification="j", job_id="job-1",
        )


def test_add_relationship_cycle_not_rejected_for_different_type(kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    _create_node(kuzu_conn, "c", "C", "cat")
    add_relationship(kuzu_conn, source_id="a", target_id="b", type="subtopic-of", justification="j", job_id="job-1")
    add_relationship(kuzu_conn, source_id="b", target_id="c", type="subtopic-of", justification="j", job_id="job-1")

    record = add_relationship(
        kuzu_conn, source_id="c", target_id="a", type="related-to",
        justification="j", job_id="job-1",
    )
    assert record.type == "related-to"


def test_add_relationship_cycle_rejected_long_chain_past_default_kuzu_cap(kuzu_conn):
    chain_length = 34  # well past Kùzu's undocumented 30-hop default cap
    node_ids = [f"n{i}" for i in range(chain_length + 1)]
    for node_id in node_ids:
        _create_node(kuzu_conn, node_id, node_id, "cat")
    for i in range(chain_length):
        add_relationship(
            kuzu_conn, source_id=node_ids[i], target_id=node_ids[i + 1], type="subtopic-of",
            justification="j", job_id="job-chain",
        )

    assert would_create_cycle(
        kuzu_conn, source_id=node_ids[-1], target_id=node_ids[0], edge_type="subtopic-of", job_id="job-chain"
    )
    with pytest.raises(CyclicRelationshipError):
        add_relationship(
            kuzu_conn, source_id=node_ids[-1], target_id=node_ids[0], type="subtopic-of",
            justification="j", job_id="job-chain",
        )


# --- durability across independent connections -----------------------------


def test_add_relationship_durable_across_independent_connections(kuzu_conn, tmp_path):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    add_relationship(
        kuzu_conn, source_id="a", target_id="b", type="related-to",
        justification="j", job_id="job-1",
    )

    independent_db = kuzu.Database(str(tmp_path / "graph"))
    independent_conn = kuzu.Connection(independent_db)
    result = independent_conn.execute(
        "MATCH (a:Concept {id: 'a'})-[r:RELATES_TO]->(b:Concept {id: 'b'}) "
        "WHERE r.type = 'related-to' RETURN r.status, r.job_id, r.justification"
    )
    assert result.has_next()
    status, job_id, justification = result.get_next()
    assert (status, job_id, justification) == ("pending", "job-1", "j")


# --- update_relationship ----------------------------------------------------


def test_update_relationship_happy_path(kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    add_relationship(
        kuzu_conn, source_id="a", target_id="b", type="related-to",
        justification="original", note="orig note", confidence=0.5, job_id="job-1",
    )

    updated = update_relationship(
        kuzu_conn, source_id="a", target_id="b", type="related-to", job_id="job-1",
        note="new note", justification="new justification", confidence=0.9,
    )

    assert updated.note == "new note"
    assert updated.justification == "new justification"
    assert updated.confidence == pytest.approx(0.9)

    stored = [r for r in search_relationships(kuzu_conn, "a") if r.type == "related-to"][0]
    assert stored.note == "new note"
    assert stored.justification == "new justification"
    assert stored.confidence == pytest.approx(0.9)


def test_update_relationship_partial_update_leaves_other_fields(kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    add_relationship(
        kuzu_conn, source_id="a", target_id="b", type="related-to",
        justification="original", note="orig note", confidence=0.5, job_id="job-1",
    )

    updated = update_relationship(
        kuzu_conn, source_id="a", target_id="b", type="related-to", job_id="job-1",
        note="only note changes",
    )

    assert updated.note == "only note changes"
    assert updated.justification == "original"
    assert updated.confidence == pytest.approx(0.5)


def test_update_relationship_not_found_raises(kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")

    with pytest.raises(RelationshipNotFoundError):
        update_relationship(
            kuzu_conn, source_id="a", target_id="b", type="related-to", job_id="job-1",
            note="doesn't matter",
        )


# --- remove_relationship -----------------------------------------------------


def test_remove_relationship_happy_path(kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")
    add_relationship(
        kuzu_conn, source_id="a", target_id="b", type="related-to",
        justification="j", job_id="job-1",
    )

    remove_relationship(kuzu_conn, source_id="a", target_id="b", type="related-to", job_id="job-1")

    assert search_relationships(kuzu_conn, "a") == []


def test_remove_relationship_not_found_raises(kuzu_conn):
    _create_node(kuzu_conn, "a", "A", "cat")
    _create_node(kuzu_conn, "b", "B", "cat")

    with pytest.raises(RelationshipNotFoundError):
        remove_relationship(kuzu_conn, source_id="a", target_id="b", type="related-to", job_id="job-1")

import shutil

import kuzu
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.text_agent import TextAgentOutput
from app.core.config import get_server_config
from app.db.kuzu_db import get_kuzu_connection
from app.db.models import Concept, Job, Source
from app.orchestrator.tools import (
    MAX_VALIDATION_RETRIES,
    commit_job,
    get_source_signals,
    has_no_progress,
    rollback_job,
    should_run_graph_agent,
)


@pytest.fixture
def kuzu_conn(tmp_path, monkeypatch):
    """Same fixture shape as `tests/test_graph_repo.py`/`tests/test_mcp_server.py`."""
    monkeypatch.setattr(get_server_config(), "kuzu_db_path", tmp_path / "graph")
    conn = get_kuzu_connection(tmp_path / "graph")
    yield conn
    get_kuzu_connection.cache_clear()
    shutil.rmtree(tmp_path / "graph", ignore_errors=True)


async def _make_job(session: AsyncSession, job_id: str) -> Job:
    job = Job(id=job_id, source_id="src-1", status="running")
    session.add(job)
    await session.flush()
    return job


def _create_kuzu_node(conn: kuzu.Connection, concept_id: str, title: str, category: str) -> None:
    conn.execute(
        "CREATE (:Concept {id: $id, title: $title, category: $category})",
        {"id": concept_id, "title": title, "category": category},
    )


def _create_kuzu_edge(
    conn: kuzu.Connection, source_id: str, target_id: str, *, job_id: str, status: str = "pending"
) -> None:
    conn.execute(
        "MATCH (a:Concept {id: $source}), (b:Concept {id: $target}) "
        "CREATE (a)-[:RELATES_TO {type: 'related-to', note: '', justification: 'j', "
        "confidence: 0.9, status: $status, job_id: $job_id, created_at: current_timestamp()}]->(b)",
        {"source": source_id, "target": target_id, "status": status, "job_id": job_id},
    )


def _kuzu_edge_status(conn: kuzu.Connection, source_id: str, target_id: str) -> str:
    result = conn.execute(
        "MATCH (a:Concept {id: $source})-[r:RELATES_TO]->(b:Concept {id: $target}) RETURN r.status",
        {"source": source_id, "target": target_id},
    )
    return result.get_next()[0]


def _kuzu_edge_exists(conn: kuzu.Connection, source_id: str, target_id: str) -> bool:
    result = conn.execute(
        "MATCH (a:Concept {id: $source})-[r:RELATES_TO]->(b:Concept {id: $target}) RETURN count(r)",
        {"source": source_id, "target": target_id},
    )
    return result.get_next()[0] > 0


# --- get_source_signals -----------------------------------------------------


@pytest.mark.asyncio
async def test_get_source_signals_high_similarity_for_matching_content(db_session: AsyncSession):
    db_session.add(
        Concept(
            title="Backpropagation",
            category="neural-networks",
            body="...",
            metadata_={},
            status="committed",
        )
    )
    source = Source(content="Backpropagation", topic_hint=None)
    db_session.add(source)
    await db_session.flush()

    signals = await get_source_signals(db_session, source.id)

    assert signals.max_title_similarity > 0.9


@pytest.mark.asyncio
async def test_get_source_signals_low_similarity_for_unrelated_content(db_session: AsyncSession):
    db_session.add(
        Concept(
            title="Backpropagation",
            category="neural-networks",
            body="...",
            metadata_={},
            status="committed",
        )
    )
    source = Source(content="zzz qqq xxx wholly unrelated filler text", topic_hint=None)
    db_session.add(source)
    await db_session.flush()

    signals = await get_source_signals(db_session, source.id)

    assert signals.max_title_similarity < 0.3


@pytest.mark.asyncio
async def test_get_source_signals_zero_similarity_when_no_concepts_exist(db_session: AsyncSession):
    source = Source(content="anything at all", topic_hint=None)
    db_session.add(source)
    await db_session.flush()

    signals = await get_source_signals(db_session, source.id)

    assert signals.max_title_similarity == 0.0


@pytest.mark.asyncio
async def test_get_source_signals_content_length_matches_source(db_session: AsyncSession):
    content = "x" * 1234
    source = Source(content=content, topic_hint=None)
    db_session.add(source)
    await db_session.flush()

    signals = await get_source_signals(db_session, source.id)

    assert signals.content_length == 1234


@pytest.mark.asyncio
async def test_get_source_signals_passes_through_topic_hint(db_session: AsyncSession):
    source = Source(content="some study notes", topic_hint="prompt engineering")
    db_session.add(source)
    await db_session.flush()

    signals = await get_source_signals(db_session, source.id)

    assert signals.topic_hint == "prompt engineering"


@pytest.mark.asyncio
async def test_get_source_signals_ignores_pending_concepts(db_session: AsyncSession):
    await _make_job(db_session, "job-a")
    db_session.add(
        Concept(
            title="Backpropagation",
            category="neural-networks",
            body="...",
            metadata_={},
            status="pending",
            job_id="job-a",
        )
    )
    source = Source(content="Backpropagation", topic_hint=None)
    db_session.add(source)
    await db_session.flush()

    signals = await get_source_signals(db_session, source.id)

    assert signals.max_title_similarity == 0.0


# --- commit_job / rollback_job -----------------------------------------------


@pytest.mark.asyncio
async def test_commit_job_flips_only_matching_job_concepts_and_edges(
    db_session: AsyncSession, kuzu_conn: kuzu.Connection
):
    await _make_job(db_session, "job-a")
    await _make_job(db_session, "job-b")
    concept1 = Concept(title="C1", category="cat", body="...", metadata_={}, status="pending", job_id="job-a")
    concept2 = Concept(title="C2", category="cat", body="...", metadata_={}, status="pending", job_id="job-a")
    other_concept = Concept(title="C3", category="cat", body="...", metadata_={}, status="pending", job_id="job-b")
    db_session.add_all([concept1, concept2, other_concept])
    await db_session.flush()

    _create_kuzu_node(kuzu_conn, "a", "A", "cat")
    _create_kuzu_node(kuzu_conn, "b", "B", "cat")
    _create_kuzu_node(kuzu_conn, "c", "C", "cat")
    _create_kuzu_node(kuzu_conn, "d", "D", "cat")
    _create_kuzu_edge(kuzu_conn, "a", "b", job_id="job-a")
    _create_kuzu_edge(kuzu_conn, "c", "d", job_id="job-b")

    await commit_job(db_session, kuzu_conn, "job-a")

    result = await db_session.execute(select(Concept).where(Concept.id.in_([concept1.id, concept2.id])))
    committed = result.scalars().all()
    assert len(committed) == 2
    assert all(c.status == "committed" for c in committed)
    assert all(c.job_id == "job-a" for c in committed)

    refreshed_other = await db_session.get(Concept, other_concept.id)
    assert refreshed_other.status == "pending"

    assert _kuzu_edge_status(kuzu_conn, "a", "b") == "committed"
    assert _kuzu_edge_status(kuzu_conn, "c", "d") == "pending"


@pytest.mark.asyncio
async def test_rollback_job_deletes_only_matching_job_pending_concepts_and_edges(
    db_session: AsyncSession, kuzu_conn: kuzu.Connection
):
    await _make_job(db_session, "job-a")
    await _make_job(db_session, "job-b")
    concept1 = Concept(title="C1", category="cat", body="...", metadata_={}, status="pending", job_id="job-a")
    concept2 = Concept(title="C2", category="cat", body="...", metadata_={}, status="pending", job_id="job-a")
    other_concept = Concept(title="C3", category="cat", body="...", metadata_={}, status="pending", job_id="job-b")
    db_session.add_all([concept1, concept2, other_concept])
    await db_session.flush()

    _create_kuzu_node(kuzu_conn, "a", "A", "cat")
    _create_kuzu_node(kuzu_conn, "b", "B", "cat")
    _create_kuzu_node(kuzu_conn, "c", "C", "cat")
    _create_kuzu_node(kuzu_conn, "d", "D", "cat")
    _create_kuzu_edge(kuzu_conn, "a", "b", job_id="job-a")
    _create_kuzu_edge(kuzu_conn, "c", "d", job_id="job-b")

    await rollback_job(db_session, kuzu_conn, "job-a")

    result = await db_session.execute(select(Concept).where(Concept.id.in_([concept1.id, concept2.id])))
    assert result.scalars().all() == []

    refreshed_other = await db_session.get(Concept, other_concept.id)
    assert refreshed_other is not None
    assert refreshed_other.status == "pending"

    assert _kuzu_edge_exists(kuzu_conn, "a", "b") is False
    assert _kuzu_edge_exists(kuzu_conn, "c", "d") is True


# --- should_run_graph_agent ---------------------------------------------------


def _text_agent_output(concepts_written: list[dict]) -> TextAgentOutput:
    return TextAgentOutput(
        segmentation=[],
        overlap_check={},
        concepts_written=concepts_written,
        raw_result_text="{}",
    )


def test_should_run_graph_agent_false_when_no_concepts_written():
    assert should_run_graph_agent(_text_agent_output([])) is False


def test_should_run_graph_agent_true_when_concept_created():
    output = _text_agent_output([{"concept_id": "c1", "title": "C1", "action": "created"}])
    assert should_run_graph_agent(output) is True


def test_should_run_graph_agent_true_when_concept_updated():
    output = _text_agent_output([{"concept_id": "c1", "title": "C1", "action": "updated"}])
    assert should_run_graph_agent(output) is True


# --- has_no_progress ----------------------------------------------------------


def _issue(category: str, target_id: str, *, severity: str = "high", description: str = "d") -> dict:
    return {"category": category, "severity": severity, "target_id": target_id, "description": description}


def test_has_no_progress_false_when_prior_issues_is_none():
    """First validation round: nothing to compare against, so it can never
    be 'no progress' regardless of how many issues this round has."""
    assert MAX_VALIDATION_RETRIES == 3
    assert has_no_progress([_issue("ungrounded_content", "c1")], None) is False


def test_has_no_progress_true_for_identical_issue_sets():
    prior = [_issue("ungrounded_content", "c1")]
    this_round = [_issue("ungrounded_content", "c1")]
    assert has_no_progress(this_round, prior) is True


def test_has_no_progress_ignores_severity_and_description_differences():
    """Settled ruling this phase: comparison key is category+target_id only
    — a changed severity/description for the same (category, target_id)
    pair still counts as the same issue persisting, i.e. no progress."""
    prior = [_issue("ungrounded_content", "c1", severity="low", description="minor drift")]
    this_round = [_issue("ungrounded_content", "c1", severity="high", description="major drift")]
    assert has_no_progress(this_round, prior) is True


def test_has_no_progress_false_for_strictly_improved_set_with_different_targets():
    prior = [_issue("ungrounded_content", "c1"), _issue("missed_duplicate", "c2")]
    this_round = [_issue("scope_overlap", "c3")]
    assert has_no_progress(this_round, prior) is False


def test_has_no_progress_false_when_all_prior_issues_resolved_and_none_remain():
    prior = [_issue("ungrounded_content", "c1")]
    this_round: list[dict] = []
    assert has_no_progress(this_round, prior) is False


def test_has_no_progress_true_when_one_persists_alongside_a_brand_new_issue():
    """Spec §5.2 step 4's literal wording ties the no-progress signal to a
    single carried-over issue ('the same issue ... was flagged last round
    too'), not to the round's issue count or set as a whole — so a
    persisting issue still triggers no-progress even if a new, different
    issue also showed up in the same round."""
    prior = [_issue("ungrounded_content", "c1")]
    this_round = [_issue("ungrounded_content", "c1"), _issue("scope_overlap", "c2")]
    assert has_no_progress(this_round, prior) is True

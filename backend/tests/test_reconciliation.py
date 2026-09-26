"""Tests for `app/jobs/reconciliation.py`: the startup sweep that cleans up
`Job` rows stuck at `status='running'` after a backend crash. Uses the same
`db_session`/`session_factory`/`kuzu_conn` fixture shapes as
`tests/test_job_service.py`/`tests/orchestrator/test_tools.py`, since this
module spans both stores exactly like `orchestrator.tools.rollback_job`.
"""

import contextlib
import shutil

import kuzu
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_server_config
from app.db.kuzu_db import get_kuzu_connection
from app.db.models import Concept, Job
from app.jobs.reconciliation import reconcile_orphaned_running_jobs


@pytest.fixture
def kuzu_conn(tmp_path, monkeypatch):
    """Same fixture shape as `tests/orchestrator/test_tools.py`."""
    monkeypatch.setattr(get_server_config(), "kuzu_db_path", tmp_path / "graph")
    conn = get_kuzu_connection(tmp_path / "graph")
    yield conn
    get_kuzu_connection.cache_clear()
    shutil.rmtree(tmp_path / "graph", ignore_errors=True)


@pytest.fixture
def session_factory(db_session: AsyncSession):
    """Same fixture shape as `tests/test_job_service.py`."""

    @contextlib.asynccontextmanager
    async def factory():
        yield db_session

    return factory


async def _make_job(db_session: AsyncSession, job_id: str, status: str) -> Job:
    job = Job(id=job_id, source_id="src-1", status=status)
    db_session.add(job)
    await db_session.flush()
    return job


def _create_kuzu_node(conn: kuzu.Connection, concept_id: str, title: str, category: str) -> None:
    conn.execute(
        "CREATE (:Concept {id: $id, title: $title, category: $category})",
        {"id": concept_id, "title": title, "category": category},
    )


def _create_kuzu_edge(conn: kuzu.Connection, source_id: str, target_id: str, *, job_id: str) -> None:
    conn.execute(
        "MATCH (a:Concept {id: $source}), (b:Concept {id: $target}) "
        "CREATE (a)-[:RELATES_TO {type: 'related-to', note: '', justification: 'j', "
        "confidence: 0.9, status: 'pending', job_id: $job_id, created_at: current_timestamp()}]->(b)",
        {"source": source_id, "target": target_id, "job_id": job_id},
    )


def _kuzu_edge_exists(conn: kuzu.Connection, source_id: str, target_id: str) -> bool:
    result = conn.execute(
        "MATCH (a:Concept {id: $source})-[r:RELATES_TO]->(b:Concept {id: $target}) RETURN count(r)",
        {"source": source_id, "target": target_id},
    )
    return result.get_next()[0] > 0


@pytest.mark.asyncio
async def test_reconciles_orphaned_running_job(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection
):
    job = await _make_job(db_session, "job-a", "running")
    concept = Concept(
        title="C1", category="cat", body="...", metadata_={}, status="pending", job_id="job-a"
    )
    db_session.add(concept)
    await db_session.flush()

    _create_kuzu_node(kuzu_conn, "a", "A", "cat")
    _create_kuzu_node(kuzu_conn, "b", "B", "cat")
    _create_kuzu_edge(kuzu_conn, "a", "b", job_id="job-a")

    reconciled_ids = await reconcile_orphaned_running_jobs(session_factory, kuzu_conn)

    assert reconciled_ids == ["job-a"]

    refreshed = await db_session.get(Job, job.id)
    assert refreshed.status == "failed"
    assert refreshed.error == "backend restarted while this job was running"

    result = await db_session.execute(select(Concept).where(Concept.id == concept.id))
    assert result.scalars().first() is None

    assert _kuzu_edge_exists(kuzu_conn, "a", "b") is False


@pytest.mark.parametrize("status", ["succeeded", "queued", "failed"])
@pytest.mark.asyncio
async def test_leaves_non_running_jobs_untouched(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, status: str
):
    job = await _make_job(db_session, "job-a", status)

    reconciled_ids = await reconcile_orphaned_running_jobs(session_factory, kuzu_conn)

    assert reconciled_ids == []
    refreshed = await db_session.get(Job, job.id)
    assert refreshed.status == status
    assert refreshed.error is None


@pytest.mark.asyncio
async def test_reconciles_multiple_orphaned_jobs_independently(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection
):
    await _make_job(db_session, "job-a", "running")
    await _make_job(db_session, "job-b", "running")
    concept_a = Concept(
        title="C1", category="cat", body="...", metadata_={}, status="pending", job_id="job-a"
    )
    concept_b = Concept(
        title="C2", category="cat", body="...", metadata_={}, status="pending", job_id="job-b"
    )
    db_session.add_all([concept_a, concept_b])
    await db_session.flush()

    _create_kuzu_node(kuzu_conn, "a", "A", "cat")
    _create_kuzu_node(kuzu_conn, "b", "B", "cat")
    _create_kuzu_node(kuzu_conn, "c", "C", "cat")
    _create_kuzu_node(kuzu_conn, "d", "D", "cat")
    _create_kuzu_edge(kuzu_conn, "a", "b", job_id="job-a")
    _create_kuzu_edge(kuzu_conn, "c", "d", job_id="job-b")

    reconciled_ids = await reconcile_orphaned_running_jobs(session_factory, kuzu_conn)

    assert set(reconciled_ids) == {"job-a", "job-b"}

    job_a = await db_session.get(Job, "job-a")
    job_b = await db_session.get(Job, "job-b")
    assert job_a.status == "failed"
    assert job_b.status == "failed"

    result = await db_session.execute(
        select(Concept).where(Concept.id.in_([concept_a.id, concept_b.id]))
    )
    assert result.scalars().all() == []

    assert _kuzu_edge_exists(kuzu_conn, "a", "b") is False
    assert _kuzu_edge_exists(kuzu_conn, "c", "d") is False

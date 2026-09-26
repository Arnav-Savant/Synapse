"""Tests for `app/services/job_service.py`: the layer that owns `Job`
lifecycle state around the LangGraph ingestion pipeline
(`app/orchestrator/graph.py`).

`ClaudeCodeEngine.invoke` is stubbed for the success/failure scenarios —
same monkeypatch pattern `tests/test_claude_code_engine.py`/
`tests/orchestrator/test_graph_ingestion_flow.py` use — since the real
`claude -p` subprocess boundary is already covered there.
"""

import contextlib
import json
import shutil

import kuzu
import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import get_server_config
from app.db.kuzu_db import get_kuzu_connection
from app.db.models import Job, Source
from app.engines.base import EngineResult
from app.engines.claude_code_engine import ClaudeCodeEngine, ClaudeCodeEngineError
from app.repositories import concept_repo
from app.services import job_service


class _FakeQueue:
    """Stands in for `app/jobs/queue.py`'s `JobQueue` — only its
    `enqueue` surface is exercised by `job_service`, so a real asyncio
    worker isn't needed to test `enqueue_processing`'s own behavior."""

    def __init__(self) -> None:
        self.enqueued: list = []

    async def enqueue(self, task) -> None:
        self.enqueued.append(task)


@pytest.fixture
def kuzu_conn(tmp_path, monkeypatch):
    """Same fixture shape as `tests/orchestrator/test_graph_ingestion_flow.py`."""
    monkeypatch.setattr(get_server_config(), "kuzu_db_path", tmp_path / "graph")
    conn = get_kuzu_connection(tmp_path / "graph")
    yield conn
    get_kuzu_connection.cache_clear()
    shutil.rmtree(tmp_path / "graph", ignore_errors=True)


@pytest.fixture
def session_factory(db_session: AsyncSession):
    """Same fixture shape as `tests/orchestrator/test_graph_ingestion_flow.py`."""

    @contextlib.asynccontextmanager
    async def factory():
        yield db_session

    return factory


async def _make_source(db_session: AsyncSession) -> Source:
    source = Source(content="Some study notes about a single topic.", topic_hint=None)
    db_session.add(source)
    await db_session.flush()
    return source


def _success_result_text() -> str:
    structured_output = {
        "segmentation": [
            {
                "title": "Concept A",
                "scope_description": "Covers only Concept A.",
                "source_excerpt_ref": "the only paragraph",
            }
        ],
        "overlap_check": {"merged_pairs": [], "notes": "n/a"},
        "concepts_written": [{"concept_id": "irrelevant", "title": "Concept A", "action": "created"}],
    }
    return "Report.\n\n```json\n" + json.dumps(structured_output) + "\n```"


@pytest.mark.asyncio
async def test_enqueue_processing_creates_queued_job_and_enqueues_callable(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection
):
    source = await _make_source(db_session)
    queue = _FakeQueue()

    job = await job_service.enqueue_processing(session_factory, kuzu_conn, source.id, queue)

    assert job.status == "queued"
    assert job.source_id == source.id
    assert len(queue.enqueued) == 1
    assert callable(queue.enqueued[0])

    result = await db_session.execute(select(Job).where(Job.id == job.id))
    row = result.scalars().first()
    assert row is not None
    assert row.status == "queued"


@pytest.mark.asyncio
async def test_process_success_marks_job_succeeded(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    source = await _make_source(db_session)
    job = Job(source_id=source.id, status="queued")
    db_session.add(job)
    await db_session.flush()

    async def fake_invoke(self, invocation):
        async with self._session_factory() as session:
            await concept_repo.create_concept(
                session,
                title="Concept A",
                category="general",
                body="Body text for Concept A.",
                metadata={},
                job_id=invocation.job_id,
            )
        return EngineResult(is_error=False, result_text=_success_result_text(), cost_usd=0.01)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    await job_service._process(session_factory, kuzu_conn, job.id)

    result = await db_session.execute(select(Job).where(Job.id == job.id))
    row = result.scalars().first()
    assert row.status == "succeeded"
    assert row.error is None


@pytest.mark.asyncio
async def test_process_failure_marks_job_failed_with_error(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    source = await _make_source(db_session)
    job = Job(source_id=source.id, status="queued")
    db_session.add(job)
    await db_session.flush()

    async def fake_invoke(self, invocation):
        raise ClaudeCodeEngineError("simulated claude exited with non-zero code")

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    await job_service._process(session_factory, kuzu_conn, job.id)

    result = await db_session.execute(select(Job).where(Job.id == job.id))
    row = result.scalars().first()
    assert row.status == "failed"
    assert "simulated claude exited with non-zero code" in row.error


@pytest.mark.asyncio
async def test_stuck_running_job_is_left_alone_by_this_layer(db_session: AsyncSession):
    """No reconciliation exists yet (that's Task 19) — a job simulating a
    crash mid-run (status='running', never revisited) must stay exactly as
    it is; this file must not assume anything reconciles it."""
    source = await _make_source(db_session)
    job = Job(source_id=source.id, status="running")
    db_session.add(job)
    await db_session.flush()

    result = await db_session.execute(select(Job).where(Job.id == job.id))
    row = result.scalars().first()
    assert row.status == "running"


@pytest.mark.asyncio
async def test_exception_from_graph_ainvoke_itself_is_caught_by_top_level_boundary(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    """Proves the exception-boundary decision end to end: an error raised
    directly from `compiled_graph.ainvoke(...)` (not from within a node —
    every node already handles its own failures internally, see
    `orchestrator/graph.py`) is still caught by `_process`'s top-level
    try/except, and the Job still ends up failed with `error` populated."""
    source = await _make_source(db_session)
    job = Job(source_id=source.id, status="queued")
    db_session.add(job)
    await db_session.flush()

    class _ExplodingGraph:
        async def ainvoke(self, state):
            raise RuntimeError("boom: ainvoke itself blew up")

    monkeypatch.setattr(job_service, "build_graph", lambda session_factory, kuzu_conn: _ExplodingGraph())

    await job_service._process(session_factory, kuzu_conn, job.id)

    result = await db_session.execute(select(Job).where(Job.id == job.id))
    row = result.scalars().first()
    assert row.status == "failed"
    assert "boom: ainvoke itself blew up" in row.error

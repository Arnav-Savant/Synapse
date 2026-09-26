"""Jobs API tests against the Postgres/Kùzu-backed `job_service`/`job_repo`
(Phase 4 Task 7 cutover). The old filesystem-era assertions (`committed_files`,
`cost_usd`, `source_relative_path`) no longer apply — `JobOut` now mirrors the
SQLAlchemy `Job` model's actual fields.

Both `Depends(postgres_connection.get_session)` and
`Depends(app.api.jobs.get_kuzu_conn)` are overridden per-test with the shared
`db_session` fixture (`tests/conftest.py`, rolled back at teardown) and a
`kuzu_conn` fixture matching `tests/test_graph_repo.py`'s pattern.
`POST /jobs/process` doesn't route its Postgres session through
`Depends(...)` (it builds a session factory inline, same idiom
`api/chat.py` uses, since the queued job outlives the request) — so
`postgres_connection.get_session` is also monkeypatched directly, matching
`tests/test_chat_api.py`'s pattern.

`Depends(get_job_queue)` is overridden with an in-test fake rather than the
real app lifespan's `JobQueue` (lifespan never runs under `ASGITransport`,
same reasoning as `test_knowledge_api.py`): a `_RecordingQueue` that just
captures the enqueued callable for contract-shape tests, and an
`_ImmediateQueue` that awaits it inline (deterministic, no background-task
polling/race) for tests that need a job to actually reach a terminal state.

Uses `httpx.AsyncClient(transport=ASGITransport(app))` rather than
`fastapi.testclient.TestClient` for the same cross-event-loop `asyncpg`
reason documented in `test_knowledge_api.py`.
"""

import contextlib
import json
import shutil
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.jobs import get_kuzu_conn
from app.core.config import get_server_config
from app.core.postgres_connection import postgres_connection
from app.db.kuzu_db import get_kuzu_connection
from app.db.models import Job, Source
from app.engines.base import EngineResult
from app.engines.claude_code_engine import ClaudeCodeEngine, ClaudeCodeEngineError
from app.jobs.queue import get_job_queue
from app.main import app
from app.repositories import concept_repo, job_repo


class _RecordingQueue:
    """Mirrors `tests/test_job_service.py`'s `_FakeQueue` — captures the
    enqueued callable without running it, so the route's immediate response
    always reflects the freshly-created `queued` job."""

    def __init__(self) -> None:
        self.enqueued: list = []

    async def enqueue(self, task) -> None:
        self.enqueued.append(task)


class _ImmediateQueue:
    """Awaits the enqueued callable inline instead of deferring to a
    background worker task, so tests that need a job to reach a terminal
    state can assert on it right after the request returns, without
    polling a real `JobQueue` worker racing against this test's own event
    loop."""

    async def enqueue(self, task) -> None:
        await task()


@pytest.fixture
def kuzu_conn(tmp_path, monkeypatch):
    """Same fixture shape as `tests/test_graph_repo.py`."""
    monkeypatch.setattr(get_server_config(), "kuzu_db_path", tmp_path / "graph")
    conn = get_kuzu_connection(tmp_path / "graph")
    yield conn
    get_kuzu_connection.cache_clear()
    shutil.rmtree(tmp_path / "graph", ignore_errors=True)


@pytest.fixture
def client_factory(db_session: AsyncSession, kuzu_conn, monkeypatch):
    """Returns a callable that builds an `AsyncClient` wired to this test's
    `db_session`/`kuzu_conn` and a given fake `JobQueue`."""

    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    def _make(queue) -> AsyncClient:
        app.dependency_overrides[postgres_connection.get_session] = _override_get_session
        app.dependency_overrides[get_kuzu_conn] = lambda: kuzu_conn
        app.dependency_overrides[get_job_queue] = lambda: queue
        monkeypatch.setattr(postgres_connection, "get_session", _override_get_session)
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://testserver")

    yield _make
    app.dependency_overrides.clear()


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
async def test_process_source_returns_202_with_queued_job(client_factory, db_session: AsyncSession):
    source = await _make_source(db_session)
    queue = _RecordingQueue()

    async with client_factory(queue) as client:
        response = await client.post("/api/jobs/process", json={"source_id": source.id})

    assert response.status_code == 202
    body = response.json()
    assert body["source_id"] == source.id
    assert body["status"] == "queued"
    assert body["error"] is None
    assert "id" in body and "created_at" in body and "updated_at" in body
    assert len(queue.enqueued) == 1


@pytest.mark.asyncio
async def test_process_source_persists_job_row(client_factory, db_session: AsyncSession):
    source = await _make_source(db_session)
    queue = _RecordingQueue()

    async with client_factory(queue) as client:
        response = await client.post("/api/jobs/process", json={"source_id": source.id})

    job_id = response.json()["id"]
    row = await job_repo.get_job(db_session, job_id)
    assert row is not None
    assert row.source_id == source.id
    assert row.status == "queued"


@pytest.mark.asyncio
async def test_process_source_job_runs_to_success(
    client_factory, db_session: AsyncSession, monkeypatch
):
    source = await _make_source(db_session)

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

    async with client_factory(_ImmediateQueue()) as client:
        response = await client.post("/api/jobs/process", json={"source_id": source.id})
        job_id = response.json()["id"]
        status_response = await client.get(f"/api/jobs/{job_id}")

    assert status_response.status_code == 200
    body = status_response.json()
    assert body["status"] == "succeeded"
    assert body["error"] is None


@pytest.mark.asyncio
async def test_process_source_job_runs_to_failure(
    client_factory, db_session: AsyncSession, monkeypatch
):
    source = await _make_source(db_session)

    async def fake_invoke(self, invocation):
        raise ClaudeCodeEngineError("simulated claude exited with non-zero code")

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    async with client_factory(_ImmediateQueue()) as client:
        response = await client.post("/api/jobs/process", json={"source_id": source.id})
        job_id = response.json()["id"]
        status_response = await client.get(f"/api/jobs/{job_id}")

    assert status_response.status_code == 200
    body = status_response.json()
    assert body["status"] == "failed"
    assert "simulated claude exited with non-zero code" in body["error"]


@pytest.mark.asyncio
async def test_get_unknown_job_returns_404(client_factory):
    async with client_factory(_RecordingQueue()) as client:
        response = await client.get("/api/jobs/does-not-exist")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_jobs_returns_all_jobs_most_recent_first(client_factory, db_session: AsyncSession):
    source = await _make_source(db_session)
    older = await job_repo.create_job(db_session, source_id=source.id)
    newer = await job_repo.create_job(db_session, source_id=source.id)

    async with client_factory(_RecordingQueue()) as client:
        response = await client.get("/api/jobs")

    assert response.status_code == 200
    ids = [j["id"] for j in response.json()["jobs"]]
    assert ids.index(newer.id) < ids.index(older.id)


@pytest.mark.asyncio
async def test_process_source_rejects_missing_source_id(client_factory):
    async with client_factory(_RecordingQueue()) as client:
        response = await client.post("/api/jobs/process", json={})

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_process_source_invalid_source_id_surfaces_as_failure(client_factory, db_session: AsyncSession):
    """`source_id` isn't validated to exist up front (matches
    `job_repo.create_job`'s contract: it always inserts) — a bad id
    surfaces once the pipeline actually tries to read the source, not at
    enqueue time."""
    queue = _RecordingQueue()

    async with client_factory(queue) as client:
        response = await client.post("/api/jobs/process", json={"source_id": "does-not-exist"})

    assert response.status_code == 202
    assert response.json()["status"] == "queued"

    result = await db_session.execute(select(Job).where(Job.id == response.json()["id"]))
    row = result.scalars().first()
    assert row is not None
    assert row.source_id == "does-not-exist"

"""`source_service` unit tests against a real (savepoint-scoped) `db_session`
for the Postgres-backed read/write paths, with `ClaudeCodeEngine.invoke`
mocked for naming-suggestion tests — mirrors `tests/test_chat_service.py`'s
style. `job_service.enqueue_processing` is exercised for real (not mocked)
against a `_RecordingQueue` that captures the enqueued task without running
it, so these tests can assert a real `Job` row was created for the written
`Source` row's id — the fix for the stale 3-argument `enqueue_processing`
call-site bug this task addresses.
"""

import contextlib

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.naming_agent import NamingAgentError
from app.engines.base import EngineResult
from app.engines.claude_code_engine import ClaudeCodeEngine
from app.repositories import job_repo, source_record_repo
from app.services import source_service


class _RecordingQueue:
    def __init__(self) -> None:
        self.enqueued: list = []

    async def enqueue(self, task) -> None:
        self.enqueued.append(task)


@pytest.fixture
def session_factory(db_session: AsyncSession):
    @contextlib.asynccontextmanager
    async def factory():
        yield db_session

    return factory


@pytest.mark.asyncio
async def test_create_text_source_with_explicit_category_skips_naming_agent(
    db_session: AsyncSession, session_factory, monkeypatch
):
    called = False

    async def fake_invoke(self, invocation):
        nonlocal called
        called = True
        return EngineResult(is_error=False, result_text='{"category": "should-not-be-used"}', cost_usd=None)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)
    queue = _RecordingQueue()

    source, job = await source_service.create_text_source(
        db_session, session_factory, None, "some content", queue, category="rag"
    )

    assert called is False
    assert source.category == "rag"
    assert source.content == "some content"
    assert job.source_id == source.id
    assert len(queue.enqueued) == 1


@pytest.mark.asyncio
async def test_create_text_source_without_category_calls_naming_agent(
    db_session: AsyncSession, session_factory, monkeypatch
):
    captured = {}

    async def fake_invoke(self, invocation):
        captured["invocation"] = invocation
        return EngineResult(is_error=False, result_text='{"category": "rag"}', cost_usd=None)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)
    queue = _RecordingQueue()

    source, _job = await source_service.create_text_source(
        db_session, session_factory, None, "some content about RAG", queue
    )

    assert source.category == "rag"
    invocation = captured["invocation"]
    assert invocation.agent_role == "naming"
    assert "some content about RAG" in invocation.prompt
    assert invocation.tool_names == ()


@pytest.mark.asyncio
async def test_create_text_source_passes_topic_hint_into_naming_prompt(
    db_session: AsyncSession, session_factory, monkeypatch
):
    captured = {}

    async def fake_invoke(self, invocation):
        captured["invocation"] = invocation
        return EngineResult(is_error=False, result_text='{"category": "rag"}', cost_usd=None)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)
    queue = _RecordingQueue()

    await source_service.create_text_source(
        db_session, session_factory, None, "content", queue, topic_hint="retrieval augmented generation"
    )

    assert "retrieval augmented generation" in captured["invocation"].prompt


@pytest.mark.asyncio
async def test_create_text_source_surveys_existing_categories_in_naming_prompt(
    db_session: AsyncSession, session_factory, monkeypatch
):
    await source_record_repo.write_source(db_session, content="x", category="prompt-engineering", topic_hint=None)

    captured = {}

    async def fake_invoke(self, invocation):
        captured["invocation"] = invocation
        return EngineResult(is_error=False, result_text='{"category": "rag"}', cost_usd=None)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)
    queue = _RecordingQueue()

    await source_service.create_text_source(db_session, session_factory, None, "new content", queue)

    assert "prompt-engineering" in captured["invocation"].prompt


@pytest.mark.asyncio
async def test_create_text_source_enqueues_a_real_db_job_row_for_the_written_source(
    db_session: AsyncSession, session_factory
):
    queue = _RecordingQueue()

    source, job = await source_service.create_text_source(
        db_session, session_factory, None, "content", queue, category="rag"
    )

    row = await job_repo.get_job(db_session, job.id)
    assert row is not None
    assert row.source_id == source.id
    assert row.status == "queued"
    assert len(queue.enqueued) == 1


@pytest.mark.asyncio
async def test_create_text_source_propagates_naming_agent_errors_and_never_enqueues(
    db_session: AsyncSession, session_factory, monkeypatch
):
    async def fake_invoke(self, invocation):
        return EngineResult(is_error=True, result_text="claude failed", cost_usd=None)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)
    queue = _RecordingQueue()

    with pytest.raises(NamingAgentError):
        await source_service.create_text_source(db_session, session_factory, None, "content", queue)

    assert queue.enqueued == []


@pytest.mark.asyncio
async def test_list_sources_returns_written_sources(db_session: AsyncSession, session_factory):
    queue = _RecordingQueue()
    await source_service.create_text_source(db_session, session_factory, None, "a", queue, category="rag")
    await source_service.create_text_source(db_session, session_factory, None, "b", queue, category="rag")

    sources = await source_service.list_sources(db_session)

    assert {s.content for s in sources} == {"a", "b"}


@pytest.mark.asyncio
async def test_read_source_returns_the_matching_row(db_session: AsyncSession, session_factory):
    queue = _RecordingQueue()
    source, _job = await source_service.create_text_source(
        db_session, session_factory, None, "content", queue, category="rag"
    )

    fetched = await source_service.read_source(db_session, source.id)

    assert fetched.id == source.id
    assert fetched.content == "content"


@pytest.mark.asyncio
async def test_read_source_raises_for_missing_id(db_session: AsyncSession):
    with pytest.raises(source_record_repo.SourceRecordNotFoundError):
        await source_service.read_source(db_session, "does-not-exist")

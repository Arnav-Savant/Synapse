"""Knowledge API tests against the Postgres/Kùzu-backed `knowledge_service`
(Phase 4 Task 12 cutover). `tests/test_knowledge_repo.py` still exercises
the retired filesystem repo directly and is left alone pending Task 18's
full retirement of that code path.

Both `Depends(postgres_connection.get_session)` and
`Depends(app.api.knowledge.get_kuzu_conn)` are overridden per-test with the
shared `db_session` fixture (`tests/conftest.py`, rolled back at teardown)
and a `kuzu_conn` fixture matching `tests/test_graph_repo.py`'s pattern.

Uses `httpx.AsyncClient(transport=ASGITransport(app))` rather than
`fastapi.testclient.TestClient`: `TestClient` dispatches each request
through an AnyIO blocking-portal thread with its own event loop, which
fails outright (`asyncpg`'s `RuntimeError: ... attached to a different
loop`, confirmed empirically) once a route dependency is overridden with
`db_session` — a real `AsyncSession`/`asyncpg` connection already bound to
this test's own (session-scoped, per `pyproject.toml`) event loop.
`AsyncClient` + `ASGITransport` calls the ASGI app in-process on the
caller's current event loop, so the overridden `db_session` is always used
from the loop it was created on. This also means lifespan never runs here
(no migrations, no job queue) — fine, since `db_session` is already
migrated via `conftest.py`'s `_migrated_engine`.
"""

import shutil
from collections.abc import AsyncIterator

import pytest
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.knowledge import get_kuzu_conn
from app.core.config import get_server_config
from app.core.postgres_connection import postgres_connection
from app.db.kuzu_db import get_kuzu_connection
from app.db.models import Concept
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
async def client(db_session: AsyncSession, kuzu_conn) -> AsyncIterator[AsyncClient]:
    async def _override_get_session() -> AsyncIterator[AsyncSession]:
        yield db_session

    app.dependency_overrides[postgres_connection.get_session] = _override_get_session
    app.dependency_overrides[get_kuzu_conn] = lambda: kuzu_conn
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as test_client:
        yield test_client
    app.dependency_overrides.clear()


async def _seed_concept(
    db_session: AsyncSession,
    kuzu_conn,
    *,
    concept_id: str,
    title: str,
    category: str = "prompt-engineering",
    body: str = "Body text.",
    metadata: dict | None = None,
    status: str = "committed",
) -> Concept:
    concept = Concept(
        id=concept_id,
        title=title,
        category=category,
        body=body,
        metadata_=metadata or {},
        status=status,
    )
    db_session.add(concept)
    await db_session.flush()
    graph_repo.ensure_node(kuzu_conn, concept_id, title, category)
    return concept


@pytest.mark.asyncio
async def test_list_knowledge_returns_only_committed_concepts(client: AsyncClient, db_session, kuzu_conn):
    await _seed_concept(db_session, kuzu_conn, concept_id="prompt-injection", title="Prompt Injection")
    await _seed_concept(
        db_session, kuzu_conn, concept_id="few-shot-prompting", title="Few-Shot Prompting", status="pending"
    )

    response = await client.get("/api/knowledge")

    assert response.status_code == 200
    assert response.json()["concepts"] == [
        {"id": "prompt-injection", "title": "Prompt Injection", "category": "prompt-engineering"}
    ]


@pytest.mark.asyncio
async def test_get_knowledge_returns_full_detail_with_relationships(client: AsyncClient, db_session, kuzu_conn):
    await _seed_concept(
        db_session,
        kuzu_conn,
        concept_id="prompt-injection",
        title="Prompt Injection",
        body="Body with detail.",
        metadata={"aliases": ["Prompt Injection Attack"], "domains": ["ai-security"]},
    )
    await _seed_concept(db_session, kuzu_conn, concept_id="prompt-engineering", title="Prompt Engineering")
    graph_repo.add_relationship(
        kuzu_conn,
        source_id="prompt-injection",
        target_id="prompt-engineering",
        type="subtopic-of",
        justification="prompt injection is a subtopic of prompt engineering",
        note="some note",
        job_id="job-1",
    )
    # knowledge_service.read_knowledge has no job context (it's a plain,
    # unauthenticated human-facing read), so it always calls
    # graph_repo.search_relationships with job_id=None — i.e. committed-only
    # (see graph_repo.get_graph_neighborhood/search_relationships job_id
    # scoping). Flip the seeded edge to committed here, same status
    # transition app/orchestrator/tools.py's commit_job performs for real,
    # so this test reflects what a human actually sees after a job lands.
    kuzu_conn.execute(
        "MATCH (a:Concept)-[r:RELATES_TO]->(b:Concept) "
        "WHERE r.job_id = $job_id AND r.status = 'pending' "
        "SET r.status = 'committed'",
        {"job_id": "job-1"},
    )

    response = await client.get("/api/knowledge/prompt-injection")

    assert response.status_code == 200
    body = response.json()
    assert body["id"] == "prompt-injection"
    assert body["title"] == "Prompt Injection"
    assert body["category"] == "prompt-engineering"
    assert body["metadata"] == {"aliases": ["Prompt Injection Attack"], "domains": ["ai-security"]}
    assert body["body"] == "Body with detail."
    assert body["relationships"] == [
        {
            "source_id": "prompt-injection",
            "target_id": "prompt-engineering",
            "type": "subtopic-of",
            "note": "some note",
        }
    ]


@pytest.mark.asyncio
async def test_get_missing_knowledge_returns_404(client: AsyncClient):
    response = await client.get("/api/knowledge/does-not-exist")

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_update_knowledge_commits_directly_and_invalidates_graph_cache(
    client: AsyncClient, db_session, kuzu_conn, monkeypatch
):
    await _seed_concept(
        db_session,
        kuzu_conn,
        concept_id="prompt-injection",
        title="Prompt Injection",
        body="Old body.",
        metadata={"aliases": []},
        status="pending",
    )

    from app.services import knowledge_service

    invalidate_calls = []
    monkeypatch.setattr(knowledge_service.graph_service, "invalidate", lambda: invalidate_calls.append(True))

    response = await client.put(
        "/api/knowledge/prompt-injection",
        json={"body": "New body.", "metadata": {"aliases": ["Injection"]}},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["body"] == "New body."
    assert body["metadata"] == {"aliases": ["Injection"]}
    assert invalidate_calls == [True]

    updated = await db_session.get(Concept, "prompt-injection")
    assert updated.body == "New body."
    assert updated.metadata_ == {"aliases": ["Injection"]}
    assert updated.status == "committed"


@pytest.mark.asyncio
async def test_update_missing_knowledge_returns_404(client: AsyncClient):
    response = await client.put(
        "/api/knowledge/does-not-exist",
        json={"body": "New body.", "metadata": {}},
    )

    assert response.status_code == 404

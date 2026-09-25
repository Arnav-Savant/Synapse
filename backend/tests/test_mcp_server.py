import contextlib
import json
import shutil

import kuzu
import pytest
from mcp.client._memory import InMemoryTransport
from mcp.client.session import ClientSession
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.config import get_server_config
from app.core.postgres_connection import postgres_connection
from app.db.kuzu_db import get_kuzu_connection
from app.db.models import Base, Concept, Job
from app.mcp_server.server import AgentRole, SynapseMcpServer, TOOL_REGISTRY
from app.repositories import concept_repo, graph_repo


@pytest.fixture
async def db_session():
    """Local duplicate of `tests/db/conftest.py`'s fixture, matching the
    convention already established in `tests/test_concept_repo.py`/
    `tests/test_source_record_repo.py`."""
    engine = postgres_connection.get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    await engine.dispose()


@pytest.fixture
def kuzu_conn(tmp_path, monkeypatch):
    """Same fixture shape as `tests/test_graph_repo.py`."""
    monkeypatch.setattr(get_server_config(), "kuzu_db_path", tmp_path / "graph")
    conn = get_kuzu_connection(tmp_path / "graph")
    yield conn
    get_kuzu_connection.cache_clear()
    shutil.rmtree(tmp_path / "graph", ignore_errors=True)


async def _make_job(session: AsyncSession, job_id: str) -> Job:
    """Commits (not just flushes) — the MCP tool call below runs against a
    different session from the same shared engine, so the row must be
    durable, not merely visible within this session's own transaction."""
    job = Job(id=job_id, source_id="src-1", status="running")
    session.add(job)
    await session.commit()
    return job


def _create_kuzu_node(conn: kuzu.Connection, concept_id: str, title: str, category: str) -> None:
    conn.execute(
        "CREATE (:Concept {id: $id, title: $title, category: $category})",
        {"id": concept_id, "title": title, "category": category},
    )


@contextlib.asynccontextmanager
async def _client_session(role: AgentRole, job_id: str, conn: kuzu.Connection):
    """Wires a real `ClientSession` to a constructed `SynapseMcpServer`
    instance's run loop in-process, over the SDK's own in-memory transport
    (`mcp.client._memory.InMemoryTransport`, empirically confirmed to exist
    in mcp 2.2.0 and to accept an `MCPServer` instance directly — it's a
    thin wrapper around `mcp.shared.memory.create_client_server_memory_streams`
    that also handles the background server task and graceful shutdown, so
    it's used here directly rather than reimplementing that task-group
    plumbing by hand)."""
    server = SynapseMcpServer(role, job_id, kuzu_conn=conn)
    async with InMemoryTransport(server._server) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()
            yield session


def _result_text(result) -> str:
    return "".join(getattr(part, "text", "") for part in result.content)


def _result_dict(result) -> dict:
    return json.loads(_result_text(result))


# --- Role-scoping (structural) ---------------------------------------------


@pytest.mark.parametrize("role", list(AgentRole))
async def test_tool_registration_matches_registry(role, kuzu_conn):
    server = SynapseMcpServer(role, job_id="job-scope", kuzu_conn=kuzu_conn)

    tools = await server._server.list_tools()

    assert {tool.name for tool in tools} == set(TOOL_REGISTRY[role])


async def test_validation_agent_has_no_write_tools(kuzu_conn):
    server = SynapseMcpServer(AgentRole.VALIDATION_AGENT, job_id="job-scope", kuzu_conn=kuzu_conn)

    tools = await server._server.list_tools()

    names = {tool.name for tool in tools}
    forbidden = {"create_concept", "update_concept", "add_relationship", "update_relationship", "remove_relationship"}
    assert names.isdisjoint(forbidden)


# --- Exception translation (the critical test) ------------------------------


async def test_add_relationship_dangling_target_translates_error(kuzu_conn):
    _create_kuzu_node(kuzu_conn, "a", "A", "cat")

    async with _client_session(AgentRole.GRAPH_AGENT, "job-1", kuzu_conn) as session:
        result = await session.call_tool(
            "add_relationship",
            {"source_id": "a", "target_id": "ghost", "type": "related-to", "justification": "j"},
        )

    assert result.is_error
    text = _result_text(result)
    assert "not found in graph" in text
    assert text != "Error executing tool add_relationship"


async def test_add_relationship_cycle_translates_error(kuzu_conn):
    _create_kuzu_node(kuzu_conn, "a", "A", "cat")
    _create_kuzu_node(kuzu_conn, "b", "B", "cat")
    _create_kuzu_node(kuzu_conn, "c", "C", "cat")
    graph_repo.add_relationship(
        kuzu_conn, source_id="a", target_id="b", type="subtopic-of", justification="j", job_id="job-1"
    )
    graph_repo.add_relationship(
        kuzu_conn, source_id="b", target_id="c", type="subtopic-of", justification="j", job_id="job-1"
    )

    async with _client_session(AgentRole.GRAPH_AGENT, "job-1", kuzu_conn) as session:
        result = await session.call_tool(
            "add_relationship",
            {"source_id": "c", "target_id": "a", "type": "subtopic-of", "justification": "j"},
        )

    assert result.is_error
    assert "would create a cycle" in _result_text(result)


async def test_add_relationship_duplicate_translates_error(kuzu_conn):
    _create_kuzu_node(kuzu_conn, "a", "A", "cat")
    _create_kuzu_node(kuzu_conn, "b", "B", "cat")
    graph_repo.add_relationship(
        kuzu_conn, source_id="a", target_id="b", type="example-of", justification="j", job_id="job-1"
    )

    async with _client_session(AgentRole.GRAPH_AGENT, "job-1", kuzu_conn) as session:
        result = await session.call_tool(
            "add_relationship",
            {"source_id": "a", "target_id": "b", "type": "example-of", "justification": "j2"},
        )

    assert result.is_error
    assert "already exists" in _result_text(result)


async def test_add_relationship_symmetric_conflict_translates_error(kuzu_conn):
    _create_kuzu_node(kuzu_conn, "a", "A", "cat")
    _create_kuzu_node(kuzu_conn, "b", "B", "cat")
    graph_repo.add_relationship(
        kuzu_conn, source_id="a", target_id="b", type="contrasts-with", justification="j", job_id="job-1"
    )

    async with _client_session(AgentRole.GRAPH_AGENT, "job-1", kuzu_conn) as session:
        result = await session.call_tool(
            "add_relationship",
            {"source_id": "b", "target_id": "a", "type": "contrasts-with", "justification": "j2"},
        )

    assert result.is_error
    text = _result_text(result)
    assert "already exists" in text
    assert "symmetric relationship" in text


# --- Happy-path round trip ---------------------------------------------------


async def test_text_agent_create_and_get_concept_round_trip(db_session, kuzu_conn):
    await _make_job(db_session, "job-text")

    async with _client_session(AgentRole.TEXT_AGENT, "job-text", kuzu_conn) as session:
        create_result = await session.call_tool(
            "create_concept",
            {"title": "Attention", "category": "transformers", "body": "Weighs input tokens.", "metadata": {"aliases": []}},
        )
        assert not create_result.is_error
        created = _result_dict(create_result)

        get_result = await session.call_tool("get_concept", {"concept_id": created["id"]})
        assert not get_result.is_error
        fetched = _result_dict(get_result)

    direct = await concept_repo.get_concept(db_session, created["id"])
    assert fetched["id"] == direct.id
    assert fetched["title"] == direct.title == "Attention"
    assert fetched["body"] == direct.body
    assert fetched["status"] == direct.status == "pending"
    assert fetched["job_id"] == direct.job_id == "job-text"


async def test_graph_agent_add_relationship_and_neighborhood_round_trip(kuzu_conn):
    _create_kuzu_node(kuzu_conn, "a", "A", "cat")
    _create_kuzu_node(kuzu_conn, "b", "B", "cat")

    async with _client_session(AgentRole.GRAPH_AGENT, "job-graph", kuzu_conn) as session:
        add_result = await session.call_tool(
            "add_relationship",
            {
                "source_id": "a", "target_id": "b", "type": "related-to",
                "justification": "j", "note": "n", "confidence": 0.8,
            },
        )
        assert not add_result.is_error
        added = _result_dict(add_result)

        neighborhood_result = await session.call_tool("get_graph_neighborhood", {"concept_id": "a", "depth": 1})
        assert not neighborhood_result.is_error
        neighborhood = _result_dict(neighborhood_result)

    direct = graph_repo.get_graph_neighborhood(kuzu_conn, "a", depth=1)
    assert added["source_id"] == "a"
    assert added["target_id"] == "b"
    assert added["status"] == "pending"
    assert added["job_id"] == "job-graph"
    assert neighborhood["center_id"] == direct.center_id
    assert {node["id"] for node in neighborhood["nodes"]} == {node.id for node in direct.nodes}
    assert {(edge["source_id"], edge["target_id"]) for edge in neighborhood["edges"]} == {
        (edge.source_id, edge.target_id) for edge in direct.edges
    }


async def test_validation_agent_get_concept_matches_direct_repo_call(db_session, kuzu_conn):
    concept = Concept(
        title="Overfitting", category="machine-learning", body="Memorizes noise instead of signal.",
        metadata_={"aliases": []}, status="committed",
    )
    db_session.add(concept)
    await db_session.commit()

    async with _client_session(AgentRole.VALIDATION_AGENT, "job-val", kuzu_conn) as session:
        result = await session.call_tool("get_concept", {"concept_id": concept.id})

    assert not result.is_error
    fetched = _result_dict(result)
    direct = await concept_repo.get_concept(db_session, concept.id)
    assert fetched["id"] == direct.id == concept.id
    assert fetched["title"] == direct.title
    assert fetched["body"] == direct.body


# --- get_concept_metadata composition ---------------------------------------


async def test_get_concept_metadata_composition_upserts_kuzu_node(db_session, kuzu_conn):
    concept = Concept(
        title="Backpropagation", category="neural-networks", body="Computes gradients via the chain rule.",
        metadata_={"aliases": []}, status="committed",
    )
    db_session.add(concept)
    await db_session.commit()

    async with _client_session(AgentRole.GRAPH_AGENT, "job-meta", kuzu_conn) as session:
        result = await session.call_tool("get_concept_metadata", {"concept_id": concept.id})

    assert not result.is_error
    fetched = _result_dict(result)
    assert fetched == {"id": concept.id, "title": "Backpropagation", "category": "neural-networks"}

    node_result = kuzu_conn.execute(
        "MATCH (c:Concept {id: $id}) RETURN c.title, c.category", {"id": concept.id}
    )
    assert node_result.has_next()
    title, category = node_result.get_next()
    assert (title, category) == ("Backpropagation", "neural-networks")

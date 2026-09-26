"""Integration test for the Phase 4 ingestion graph (`orchestrator/graph.py`):
end-to-end `assess_signals -> invoke_text_agent -> commit|rollback` against
real Postgres/Kùzu fixtures, with `ClaudeCodeEngine.invoke` stubbed (no real
`claude -p` subprocess) since that boundary is already covered by
`tests/test_claude_code_engine.py`.

The stub simulates what the real Text Agent would have done via its own MCP
tool calls (`create_concept`) as a side effect before returning its
`EngineResult`, since the graph itself never calls `create_concept` —
that's the agent's own tool dispatch inside the `claude -p` subprocess,
which is exactly what's being stood in for here.
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
from app.db.models import Concept, Job, JobRound, Source
from app.engines.base import EngineResult
from app.engines.claude_code_engine import ClaudeCodeEngine, ClaudeCodeEngineError
from app.orchestrator.graph import build_graph
from app.repositories import concept_repo, graph_repo


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
    """Same fixture shape as `tests/test_claude_code_engine.py`: wraps the
    single per-test `db_session` (itself a savepoint inside one outer
    transaction) so every `async with session_factory() as session` call
    the graph makes operates on the same transactional state, and the
    fixture's teardown rollback discards it all."""

    @contextlib.asynccontextmanager
    async def factory():
        yield db_session

    return factory


async def _make_job_and_source(db_session: AsyncSession) -> tuple[Job, Source]:
    source = Source(content="Some study notes about two distinct topics.", topic_hint=None)
    db_session.add(source)
    await db_session.flush()

    job = Job(source_id=source.id, status="running")
    db_session.add(job)
    await db_session.flush()

    return job, source


def _initial_state(job: Job, source: Source) -> dict:
    return {
        "job_id": job.id,
        "source_id": source.id,
        "signals": None,
        "text_agent_result": None,
        "should_run_graph_agent": False,
        "round_number": 0,
        "status": "running",
        "error": None,
    }


def _success_result_text(concept_a_id: str, concept_b_id: str) -> str:
    structured_output = {
        "segmentation": [
            {
                "title": "Concept A",
                "scope_description": "Covers only the definition and mechanics of Concept A.",
                "source_excerpt_ref": "first paragraph",
            },
            {
                "title": "Concept B",
                "scope_description": "Covers only Concept B's distinct, unrelated use case.",
                "source_excerpt_ref": "second paragraph",
            },
        ],
        "overlap_check": {"merged_pairs": [], "notes": "no overlap between A and B"},
        "concepts_written": [
            {"concept_id": concept_a_id, "title": "Concept A", "action": "created"},
            {"concept_id": concept_b_id, "title": "Concept B", "action": "created"},
        ],
    }
    return "Here is my report.\n\n```json\n" + json.dumps(structured_output) + "\n```"


@pytest.mark.asyncio
async def test_graph_success_path_commits_two_concepts_and_one_job_round(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    job, source = await _make_job_and_source(db_session)

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "graph_agent":
            # This test predates the Graph Agent (Phase 5) and isn't
            # exercising its behavior — since `should_run_graph_agent` now
            # correctly returns True whenever concepts were written, the
            # graph invokes it too. A no-op turn (no relationships
            # proposed) keeps this test focused on what it actually
            # asserts (Text Agent's two committed concepts + job_round),
            # without needing to model Graph Agent's own tool calls here.
            return EngineResult(
                is_error=False,
                result_text='```json\n{"relationships_written": []}\n```',
                cost_usd=0.0,
            )
        async with self._session_factory() as session:
            concept_a = await concept_repo.create_concept(
                session,
                title="Concept A",
                category="general",
                body="Body text scoped only to Concept A's mechanics.",
                metadata={},
                job_id=invocation.job_id,
            )
            concept_b = await concept_repo.create_concept(
                session,
                title="Concept B",
                category="general",
                body="Body text scoped only to Concept B's distinct use case.",
                metadata={},
                job_id=invocation.job_id,
            )
        return EngineResult(
            is_error=False,
            result_text=_success_result_text(concept_a.id, concept_b.id),
            cost_usd=0.02,
        )

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    compiled = build_graph(session_factory, kuzu_conn)
    final_state = await compiled.ainvoke(_initial_state(job, source))

    assert final_state["status"] == "succeeded"
    assert final_state["should_run_graph_agent"] is True

    result = await db_session.execute(
        select(Concept).where(Concept.job_id == job.id, Concept.status == "committed")
    )
    committed_concepts = result.scalars().all()
    assert len(committed_concepts) == 2
    bodies = {c.body for c in committed_concepts}
    assert bodies == {
        "Body text scoped only to Concept A's mechanics.",
        "Body text scoped only to Concept B's distinct use case.",
    }

    # Two rounds now: Text Agent, then Graph Agent (Phase 5) — the latter a
    # no-op turn here since this test isn't exercising Graph Agent behavior,
    # but should_run_graph_agent correctly invokes it whenever concepts were
    # written, so it genuinely runs.
    round_result = await db_session.execute(
        select(JobRound).where(JobRound.job_id == job.id).order_by(JobRound.round_number)
    )
    job_rounds = round_result.scalars().all()
    assert len(job_rounds) == 2
    assert job_rounds[0].agent_type == "text_agent"
    assert job_rounds[0].structured_output_json is not None
    assert job_rounds[0].structured_output_json["concepts_written"][0]["action"] == "created"
    assert job_rounds[1].agent_type == "graph_agent"


@pytest.mark.asyncio
async def test_graph_failure_path_rolls_back_and_reports_error(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    job, source = await _make_job_and_source(db_session)

    async def fake_invoke(self, invocation):
        # Simulates the realistic case: the agent's own MCP tool calls
        # already created a pending concept during the `claude -p`
        # subprocess run, but the invocation is then reported as failed
        # (e.g. non-zero exit/timeout) once control returns to the engine.
        async with self._session_factory() as session:
            await concept_repo.create_concept(
                session,
                title="Orphan Concept",
                category="general",
                body="Written before the invocation ultimately failed.",
                metadata={},
                job_id=invocation.job_id,
            )
        raise ClaudeCodeEngineError("simulated claude exited with non-zero code")

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    compiled = build_graph(session_factory, kuzu_conn)
    final_state = await compiled.ainvoke(_initial_state(job, source))

    assert final_state["status"] == "failed"
    assert final_state["error"] == "simulated claude exited with non-zero code"

    result = await db_session.execute(select(Concept).where(Concept.job_id == job.id))
    assert result.scalars().all() == []


# --- Phase 5: Graph Agent end-to-end (real Kùzu edge, real Layer 1 gate) ---


def _seed_committed_edge(conn: kuzu.Connection, source_id: str, target_id: str, edge_type: str) -> None:
    """Raw-Cypher seed of an already-committed relationship, same shape as
    `test_graph_repo.py`'s own `_create_edge` fixture helper — used here to
    represent graph state from a prior, already-committed job rather than
    this test's own in-flight one."""
    conn.execute(
        "MATCH (a:Concept {id: $source}), (b:Concept {id: $target}) "
        "CREATE (a)-[:RELATES_TO {type: $type, note: '', justification: 'seed', "
        "confidence: 0.9, status: 'committed', job_id: 'seed-job', "
        "created_at: current_timestamp()}]->(b)",
        {"source": source_id, "target": target_id, "type": edge_type},
    )


@pytest.mark.asyncio
async def test_graph_agent_creates_committed_relationship_with_justification(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    job, source = await _make_job_and_source(db_session)
    concept_ids: dict[str, str] = {}

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "text_agent":
            async with self._session_factory() as session:
                concept_a = await concept_repo.create_concept(
                    session,
                    title="Backpropagation",
                    category="neural-networks",
                    body="Body text about backpropagation.",
                    metadata={},
                    job_id=invocation.job_id,
                )
                concept_b = await concept_repo.create_concept(
                    session,
                    title="Gradient Descent",
                    category="neural-networks",
                    body="Body text about gradient descent.",
                    metadata={},
                    job_id=invocation.job_id,
                )
            concept_ids["a"] = concept_a.id
            concept_ids["b"] = concept_b.id
            structured_output = {
                "segmentation": [
                    {
                        "title": "Backpropagation",
                        "scope_description": "Covers only backpropagation's mechanics.",
                        "source_excerpt_ref": "first paragraph",
                    },
                    {
                        "title": "Gradient Descent",
                        "scope_description": "Covers only gradient descent's mechanics.",
                        "source_excerpt_ref": "second paragraph",
                    },
                ],
                "overlap_check": {"merged_pairs": [], "notes": "no overlap"},
                "concepts_written": [
                    {"concept_id": concept_a.id, "title": "Backpropagation", "action": "created"},
                    {"concept_id": concept_b.id, "title": "Gradient Descent", "action": "created"},
                ],
            }
            return EngineResult(
                is_error=False,
                result_text="Report.\n\n```json\n" + json.dumps(structured_output) + "\n```",
                cost_usd=0.02,
            )

        assert invocation.agent_role == "graph_agent"
        graph_repo.ensure_node(kuzu_conn, concept_ids["a"], "Backpropagation", "neural-networks")
        graph_repo.ensure_node(kuzu_conn, concept_ids["b"], "Gradient Descent", "neural-networks")
        graph_repo.add_relationship(
            kuzu_conn,
            source_id=concept_ids["a"],
            target_id=concept_ids["b"],
            type="related-to",
            justification="both concepts appear together in this job's Text Agent output",
            job_id=invocation.job_id,
        )
        relationships_output = {
            "relationships_written": [
                {
                    "source_id": concept_ids["a"],
                    "target_id": concept_ids["b"],
                    "type": "related-to",
                    "action": "created",
                }
            ]
        }
        return EngineResult(
            is_error=False,
            result_text="Report.\n\n```json\n" + json.dumps(relationships_output) + "\n```",
            cost_usd=0.01,
        )

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    compiled = build_graph(session_factory, kuzu_conn)
    final_state = await compiled.ainvoke(_initial_state(job, source))

    assert final_state["status"] == "succeeded"

    relationships = graph_repo.search_relationships(kuzu_conn, concept_ids["a"])
    edge = next(
        r
        for r in relationships
        if r.source_id == concept_ids["a"] and r.target_id == concept_ids["b"]
    )
    assert edge.type == "related-to"
    assert edge.justification
    assert edge.status == "committed"

    round_result = await db_session.execute(
        select(JobRound).where(JobRound.job_id == job.id, JobRound.agent_type == "graph_agent")
    )
    graph_rounds = round_result.scalars().all()
    assert len(graph_rounds) == 1
    assert graph_rounds[0].structured_output_json is not None
    assert graph_rounds[0].structured_output_json["relationships_written"][0]["action"] == "created"


@pytest.mark.asyncio
async def test_graph_agent_cyclic_relationship_rejected_before_staging(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    job, source = await _make_job_and_source(db_session)

    graph_repo.ensure_node(kuzu_conn, "a", "A", "cat")
    graph_repo.ensure_node(kuzu_conn, "b", "B", "cat")
    graph_repo.ensure_node(kuzu_conn, "c", "C", "cat")
    _seed_committed_edge(kuzu_conn, "a", "b", "subtopic-of")
    _seed_committed_edge(kuzu_conn, "b", "c", "subtopic-of")

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "text_agent":
            async with self._session_factory() as session:
                concept_a = await concept_repo.create_concept(
                    session,
                    title="Unrelated Concept A",
                    category="general",
                    body="Body text unrelated to the seeded a/b/c chain.",
                    metadata={},
                    job_id=invocation.job_id,
                )
                concept_b = await concept_repo.create_concept(
                    session,
                    title="Unrelated Concept B",
                    category="general",
                    body="Body text unrelated to the seeded a/b/c chain.",
                    metadata={},
                    job_id=invocation.job_id,
                )
            structured_output = {
                "segmentation": [
                    {
                        "title": "Unrelated Concept A",
                        "scope_description": "Covers only Concept A.",
                        "source_excerpt_ref": "first paragraph",
                    },
                    {
                        "title": "Unrelated Concept B",
                        "scope_description": "Covers only Concept B.",
                        "source_excerpt_ref": "second paragraph",
                    },
                ],
                "overlap_check": {"merged_pairs": [], "notes": "no overlap"},
                "concepts_written": [
                    {"concept_id": concept_a.id, "title": "Unrelated Concept A", "action": "created"},
                    {"concept_id": concept_b.id, "title": "Unrelated Concept B", "action": "created"},
                ],
            }
            return EngineResult(
                is_error=False,
                result_text="Report.\n\n```json\n" + json.dumps(structured_output) + "\n```",
                cost_usd=0.02,
            )

        assert invocation.agent_role == "graph_agent"
        relationships_written: list[dict] = []
        try:
            # Mirrors what the real MCP tool-translation layer does: a
            # domain exception (CyclicRelationshipError) becomes a ToolError
            # the agent's own subprocess sees and reacts to, never a raw
            # Python exception propagating out to our orchestrator code.
            graph_repo.add_relationship(
                kuzu_conn,
                source_id="c",
                target_id="a",
                type="subtopic-of",
                justification="closing the loop back to a",
                job_id=invocation.job_id,
            )
            relationships_written.append(
                {"source_id": "c", "target_id": "a", "type": "subtopic-of", "action": "created"}
            )
        except graph_repo.CyclicRelationshipError:
            pass

        return EngineResult(
            is_error=False,
            result_text=(
                "Report.\n\n```json\n"
                + json.dumps({"relationships_written": relationships_written})
                + "\n```"
            ),
            cost_usd=0.01,
        )

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    compiled = build_graph(session_factory, kuzu_conn)
    final_state = await compiled.ainvoke(_initial_state(job, source))

    assert final_state["status"] == "succeeded"

    result = kuzu_conn.execute(
        "MATCH (x:Concept {id: 'c'})-[r:RELATES_TO {type: 'subtopic-of'}]->(y:Concept {id: 'a'}) "
        "RETURN count(r)"
    )
    assert result.get_next()[0] == 0

    with pytest.raises(graph_repo.CyclicRelationshipError):
        graph_repo.add_relationship(
            kuzu_conn,
            source_id="c",
            target_id="a",
            type="subtopic-of",
            justification="closing the loop back to a",
            job_id=job.id,
        )

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
from app.mcp_server.server import AgentRole
from app.orchestrator.graph import build_graph
from app.orchestrator.tools import MAX_SYNTHESIZED_NODES
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
        "synthesized_node_count": 0,
    }


_PASS_VALIDATION_RESULT_TEXT = '```json\n{"verdict": "pass", "issues": []}\n```'


def _reject_validation_result_text(issues: list[dict]) -> str:
    return "```json\n" + json.dumps({"verdict": "reject", "issues": issues}) + "\n```"


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
        if invocation.agent_role == "validation_agent":
            # This test predates the Validation Agent (Phase 6) and isn't
            # exercising its behavior — a "pass" verdict keeps this test
            # focused on what it actually asserts.
            return EngineResult(is_error=False, result_text=_PASS_VALIDATION_RESULT_TEXT, cost_usd=0.0)
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

    # Three rounds now: Text Agent, Graph Agent (Phase 5, a no-op turn here
    # since this test isn't exercising Graph Agent behavior, but
    # should_run_graph_agent correctly invokes it whenever concepts were
    # written), then Validation Agent (Phase 6, a "pass" verdict here since
    # this test isn't exercising the retry loop).
    round_result = await db_session.execute(
        select(JobRound).where(JobRound.job_id == job.id).order_by(JobRound.round_number)
    )
    job_rounds = round_result.scalars().all()
    assert len(job_rounds) == 3
    assert job_rounds[0].agent_type == "text_agent"
    assert job_rounds[0].structured_output_json is not None
    assert job_rounds[0].structured_output_json["concepts_written"][0]["action"] == "created"
    assert job_rounds[1].agent_type == "graph_agent"
    assert job_rounds[2].agent_type == "validation_agent"


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

        if invocation.agent_role == "validation_agent":
            return EngineResult(is_error=False, result_text=_PASS_VALIDATION_RESULT_TEXT, cost_usd=0.0)

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

        if invocation.agent_role == "validation_agent":
            return EngineResult(is_error=False, result_text=_PASS_VALIDATION_RESULT_TEXT, cost_usd=0.0)

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


# --- Task 6: critique-delta consume-and-clear wiring ---


@pytest.mark.asyncio
async def test_text_agent_critique_delta_is_passed_to_prompt_and_cleared_on_success(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    job, source = await _make_job_and_source(db_session)
    delta = "Last round missed the distinction between A and B — be more precise this time."
    captured_prompts: dict[str, str] = {}

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "graph_agent":
            return EngineResult(
                is_error=False,
                result_text='```json\n{"relationships_written": []}\n```',
                cost_usd=0.0,
            )
        if invocation.agent_role == "validation_agent":
            return EngineResult(is_error=False, result_text=_PASS_VALIDATION_RESULT_TEXT, cost_usd=0.0)
        captured_prompts["text_agent"] = invocation.prompt
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
    initial_state = {**_initial_state(job, source), "text_agent_critique_delta": delta}
    final_state = await compiled.ainvoke(initial_state)

    assert final_state["status"] == "succeeded"
    assert delta in captured_prompts["text_agent"]
    assert final_state["text_agent_critique_delta"] is None


@pytest.mark.asyncio
async def test_graph_agent_critique_delta_is_passed_to_prompt_and_cleared_on_success(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    job, source = await _make_job_and_source(db_session)
    delta = "Last round proposed a bogus relationship type — double check the taxonomy."
    captured_prompts: dict[str, str] = {}

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "graph_agent":
            captured_prompts["graph_agent"] = invocation.prompt
            return EngineResult(
                is_error=False,
                result_text='```json\n{"relationships_written": []}\n```',
                cost_usd=0.0,
            )
        if invocation.agent_role == "validation_agent":
            return EngineResult(is_error=False, result_text=_PASS_VALIDATION_RESULT_TEXT, cost_usd=0.0)
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
    initial_state = {**_initial_state(job, source), "graph_agent_critique_delta": delta}
    final_state = await compiled.ainvoke(initial_state)

    assert final_state["status"] == "succeeded"
    assert delta in captured_prompts["graph_agent"]
    assert final_state["graph_agent_critique_delta"] is None


@pytest.mark.asyncio
async def test_absent_critique_deltas_leave_prompts_and_state_unchanged(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    job, source = await _make_job_and_source(db_session)
    captured_prompts: dict[str, str] = {}

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "graph_agent":
            captured_prompts["graph_agent"] = invocation.prompt
            return EngineResult(
                is_error=False,
                result_text='```json\n{"relationships_written": []}\n```',
                cost_usd=0.0,
            )
        if invocation.agent_role == "validation_agent":
            return EngineResult(is_error=False, result_text=_PASS_VALIDATION_RESULT_TEXT, cost_usd=0.0)
        captured_prompts["text_agent"] = invocation.prompt
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
    assert "Additional guidance for this run" not in captured_prompts["text_agent"]
    assert "Additional guidance for this run" not in captured_prompts["graph_agent"]
    assert final_state.get("text_agent_critique_delta") is None
    assert final_state.get("graph_agent_critique_delta") is None


# --- Task 7: Validation Agent + retry loop ---


def _no_op_text_agent_result_text() -> str:
    """concepts_written=[] keeps should_run_graph_agent False, so these
    tests exercise the Text Agent <-> Validation Agent loop directly
    without also needing to model Graph Agent behavior."""
    structured_output = {
        "segmentation": [],
        "overlap_check": {"merged_pairs": [], "notes": "n/a"},
        "concepts_written": [],
    }
    return "```json\n" + json.dumps(structured_output) + "\n```"


@pytest.mark.asyncio
async def test_validation_pass_routes_straight_to_commit(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    job, source = await _make_job_and_source(db_session)

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "validation_agent":
            return EngineResult(is_error=False, result_text=_PASS_VALIDATION_RESULT_TEXT, cost_usd=0.0)
        assert invocation.agent_role == "text_agent"
        return EngineResult(is_error=False, result_text=_no_op_text_agent_result_text(), cost_usd=0.01)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    compiled = build_graph(session_factory, kuzu_conn)
    final_state = await compiled.ainvoke(_initial_state(job, source))

    assert final_state["status"] == "succeeded"
    assert final_state["validation_result"]["verdict"] == "pass"
    assert final_state.get("text_agent_critique_delta") is None
    assert final_state.get("graph_agent_critique_delta") is None

    round_result = await db_session.execute(
        select(JobRound).where(JobRound.job_id == job.id).order_by(JobRound.round_number)
    )
    assert [r.agent_type for r in round_result.scalars().all()] == ["text_agent", "validation_agent"]


@pytest.mark.asyncio
async def test_validation_reject_with_progress_retries_targeted_agent(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    job, source = await _make_job_and_source(db_session)
    text_agent_prompts: list[str] = []
    validation_calls = {"count": 0}
    first_round_issues = [
        {
            "category": "ungrounded_content",
            "severity": "high",
            "target_id": "concept-1",
            "description": "Concept 1's body isn't grounded in its cited excerpt.",
        }
    ]

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "validation_agent":
            validation_calls["count"] += 1
            if validation_calls["count"] == 1:
                return EngineResult(
                    is_error=False,
                    result_text=_reject_validation_result_text(first_round_issues),
                    cost_usd=0.0,
                )
            return EngineResult(is_error=False, result_text=_PASS_VALIDATION_RESULT_TEXT, cost_usd=0.0)
        assert invocation.agent_role == "text_agent"
        text_agent_prompts.append(invocation.prompt)
        return EngineResult(is_error=False, result_text=_no_op_text_agent_result_text(), cost_usd=0.01)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    compiled = build_graph(session_factory, kuzu_conn)
    final_state = await compiled.ainvoke(_initial_state(job, source))

    assert final_state["status"] == "succeeded"
    assert len(text_agent_prompts) == 2
    # The critique delta from round 1's rejection reached round 2's Text
    # Agent prompt (populated by invoke_validation_agent, consumed+cleared
    # by invoke_text_agent's own success path — Task 6, unchanged here).
    assert "Validation Agent rejected the previous round" in text_agent_prompts[1]
    assert "ungrounded_content" in text_agent_prompts[1]
    assert "concept-1" in text_agent_prompts[1]
    assert final_state.get("text_agent_critique_delta") is None
    assert final_state["retry_count"] == 1
    assert final_state["prior_validation_issues"] == first_round_issues


@pytest.mark.asyncio
async def test_validation_reject_with_no_progress_escalates_instead_of_retrying(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    job, source = await _make_job_and_source(db_session)
    text_agent_calls = {"count": 0}
    repeated_issue = {
        "category": "ungrounded_content",
        "severity": "high",
        "target_id": "concept-1",
        "description": "Concept 1's body isn't grounded in its cited excerpt.",
    }

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "validation_agent":
            # Same (category, target_id) as the seeded prior round below —
            # spec §5.2 step 4's no-progress signal.
            return EngineResult(
                is_error=False,
                result_text=_reject_validation_result_text([repeated_issue]),
                cost_usd=0.0,
            )
        assert invocation.agent_role == "text_agent"
        text_agent_calls["count"] += 1
        async with self._session_factory() as session:
            await concept_repo.create_concept(
                session,
                title="Orphan Concept",
                category="general",
                body="Written before this round's validation escalated.",
                metadata={},
                job_id=invocation.job_id,
            )
        return EngineResult(is_error=False, result_text=_no_op_text_agent_result_text(), cost_usd=0.01)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    compiled = build_graph(session_factory, kuzu_conn)
    initial_state = {
        **_initial_state(job, source),
        "prior_validation_issues": [repeated_issue],
        "retry_count": 1,
    }
    final_state = await compiled.ainvoke(initial_state)

    assert final_state["status"] == "needs_review"
    assert text_agent_calls["count"] == 1  # not re-invoked — escalated instead
    assert final_state.get("text_agent_critique_delta") is None
    assert final_state.get("graph_agent_critique_delta") is None
    assert final_state["retry_count"] == 1  # budget not spent on a no-progress round

    # Spec §5.2 step 7: escalation rolls back all staged writes for this job.
    result = await db_session.execute(select(Concept).where(Concept.job_id == job.id))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_validation_hits_retry_cap_escalates_despite_genuine_progress(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    job, source = await _make_job_and_source(db_session)
    text_agent_calls = {"count": 0}
    validation_calls = {"count": 0}

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "validation_agent":
            validation_calls["count"] += 1
            # A distinct (category, target_id) every round — genuine
            # progress each time, per Task 5's settled has_no_progress
            # semantics — yet the hard retry cap (spec §5.2 step 6: "up to
            # a hard retry cap, regardless of the no-progress check") still
            # terminates the loop on its own.
            issue = {
                "category": "ungrounded_content",
                "severity": "high",
                "target_id": f"concept-{validation_calls['count']}",
                "description": "Still not grounded this round either.",
            }
            return EngineResult(
                is_error=False,
                result_text=_reject_validation_result_text([issue]),
                cost_usd=0.0,
            )
        assert invocation.agent_role == "text_agent"
        text_agent_calls["count"] += 1
        return EngineResult(is_error=False, result_text=_no_op_text_agent_result_text(), cost_usd=0.01)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    compiled = build_graph(session_factory, kuzu_conn)
    final_state = await compiled.ainvoke(_initial_state(job, source))

    assert final_state["status"] == "needs_review"
    # MAX_VALIDATION_RETRIES=3: an initial round plus 3 retries before the
    # 4th validation call finds retry_count already at the cap and escalates.
    assert text_agent_calls["count"] == 4
    assert validation_calls["count"] == 4
    assert final_state["retry_count"] == 3


@pytest.mark.asyncio
async def test_validation_malformed_verdict_routes_to_rollback_as_failed(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    job, source = await _make_job_and_source(db_session)

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "validation_agent":
            return EngineResult(
                is_error=False,
                result_text='```json\n{"verdict": "maybe", "issues": []}\n```',
                cost_usd=0.0,
            )
        assert invocation.agent_role == "text_agent"
        return EngineResult(is_error=False, result_text=_no_op_text_agent_result_text(), cost_usd=0.01)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    compiled = build_graph(session_factory, kuzu_conn)
    final_state = await compiled.ainvoke(_initial_state(job, source))

    assert final_state["status"] == "failed"
    assert "invalid verdict" in final_state["error"]


@pytest.mark.asyncio
async def test_validation_unknown_category_routes_to_rollback_as_failed(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    job, source = await _make_job_and_source(db_session)

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "validation_agent":
            issue = {
                "category": "not_a_real_category",
                "severity": "high",
                "target_id": "concept-1",
                "description": "n/a",
            }
            return EngineResult(
                is_error=False,
                result_text=_reject_validation_result_text([issue]),
                cost_usd=0.0,
            )
        assert invocation.agent_role == "text_agent"
        return EngineResult(is_error=False, result_text=_no_op_text_agent_result_text(), cost_usd=0.01)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    compiled = build_graph(session_factory, kuzu_conn)
    final_state = await compiled.ainvoke(_initial_state(job, source))

    assert final_state["status"] == "failed"
    assert "unrecognized validation issue category" in final_state["error"]


@pytest.mark.asyncio
async def test_validation_reject_with_empty_issues_routes_to_rollback_as_failed(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    job, source = await _make_job_and_source(db_session)

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "validation_agent":
            return EngineResult(
                is_error=False,
                result_text=_reject_validation_result_text([]),
                cost_usd=0.0,
            )
        assert invocation.agent_role == "text_agent"
        return EngineResult(is_error=False, result_text=_no_op_text_agent_result_text(), cost_usd=0.01)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    compiled = build_graph(session_factory, kuzu_conn)
    final_state = await compiled.ainvoke(_initial_state(job, source))

    assert final_state["status"] == "failed"
    assert "empty issues list" in final_state["error"]


@pytest.mark.asyncio
async def test_validation_reject_spanning_both_agents_cascades_without_delta_leakage(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    """A single reject round with one text_agent-category issue and one
    graph_agent-category issue must populate both critique deltas, and each
    specialist's *own* re-invocation prompt must show only its own delta —
    not the other specialist's — confirming the two deltas don't clobber or
    leak into each other across the should_run_graph_agent cascade."""
    job, source = await _make_job_and_source(db_session)
    text_agent_calls = {"count": 0}
    graph_agent_calls = {"count": 0}
    validation_calls = {"count": 0}
    text_agent_prompts: list[str] = []
    graph_agent_prompts: list[str] = []
    first_round_issues = [
        {
            "category": "missed_duplicate",
            "severity": "medium",
            "target_id": "concept-1",
            "description": "Concept 1 duplicates an existing concept.",
        },
        {
            "category": "unsupported_justification",
            "severity": "high",
            "target_id": "edge-1",
            "description": "Edge 1's justification doesn't establish the claim.",
        },
    ]

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "validation_agent":
            validation_calls["count"] += 1
            if validation_calls["count"] == 1:
                return EngineResult(
                    is_error=False,
                    result_text=_reject_validation_result_text(first_round_issues),
                    cost_usd=0.0,
                )
            return EngineResult(is_error=False, result_text=_PASS_VALIDATION_RESULT_TEXT, cost_usd=0.0)
        if invocation.agent_role == "graph_agent":
            graph_agent_calls["count"] += 1
            graph_agent_prompts.append(invocation.prompt)
            return EngineResult(
                is_error=False,
                result_text='```json\n{"relationships_written": []}\n```',
                cost_usd=0.0,
            )
        assert invocation.agent_role == "text_agent"
        text_agent_calls["count"] += 1
        text_agent_prompts.append(invocation.prompt)
        # Non-empty concepts_written every round so should_run_graph_agent
        # cascades Graph Agent after each Text Agent re-invocation too.
        structured_output = {
            "segmentation": [],
            "overlap_check": {"merged_pairs": [], "notes": "n/a"},
            "concepts_written": [
                {"concept_id": f"concept-{text_agent_calls['count']}", "title": "C", "action": "created"}
            ],
        }
        return EngineResult(
            is_error=False,
            result_text="```json\n" + json.dumps(structured_output) + "\n```",
            cost_usd=0.01,
        )

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    compiled = build_graph(session_factory, kuzu_conn)
    final_state = await compiled.ainvoke(_initial_state(job, source))

    assert final_state["status"] == "succeeded"
    assert text_agent_calls["count"] == 2
    assert graph_agent_calls["count"] == 2
    assert validation_calls["count"] == 2

    round_2_text_prompt = text_agent_prompts[1]
    assert "missed_duplicate" in round_2_text_prompt
    assert "concept-1" in round_2_text_prompt
    assert "unsupported_justification" not in round_2_text_prompt
    assert "edge-1" not in round_2_text_prompt

    round_2_graph_prompt = graph_agent_prompts[1]
    assert "unsupported_justification" in round_2_graph_prompt
    assert "edge-1" in round_2_graph_prompt
    assert "missed_duplicate" not in round_2_graph_prompt
    assert "concept-1" not in round_2_graph_prompt

    assert final_state.get("text_agent_critique_delta") is None
    assert final_state.get("graph_agent_critique_delta") is None
    assert final_state["retry_count"] == 1
    assert final_state["prior_validation_issues"] == first_round_issues


# --- Task 5: Structural gap synthesis loop ---


def _gap_flagging_relationships_output(member_ids: list[str]) -> str:
    payload = {
        "relationships_written": [],
        "structural_gaps": [
            {
                "gap_type": "missing_parent",
                "member_concept_ids": member_ids,
                "proposed_title": "Neural Networks",
                "proposed_scope_hint": "The umbrella topic covering both members.",
                "justification": f"{member_ids[0]} and {member_ids[1]} share no common ancestor within 2 hops.",
            }
        ],
    }
    return "```json\n" + json.dumps(payload) + "\n```"


_GAP_SYNTHESIS_PROMPT_MARKER = "invoked to synthesize a new concept"


@pytest.mark.asyncio
async def test_structural_gap_synthesizes_parent_and_resumes_graph_agent(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    job, source = await _make_job_and_source(db_session)
    concept_ids: dict[str, str] = {}
    graph_agent_calls = {"count": 0}
    text_agent_gap_prompts: list[str] = []
    gap_synthesis_agent_roles: list[str] = []

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "validation_agent":
            return EngineResult(is_error=False, result_text=_PASS_VALIDATION_RESULT_TEXT, cost_usd=0.0)

        if invocation.agent_role == "graph_agent":
            graph_agent_calls["count"] += 1
            if graph_agent_calls["count"] == 1:
                return EngineResult(
                    is_error=False,
                    result_text=_gap_flagging_relationships_output(
                        [concept_ids["a"], concept_ids["b"]]
                    ),
                    cost_usd=0.01,
                )
            # Resume round: attach the two siblings to the newly synthesized parent.
            graph_repo.ensure_node(kuzu_conn, concept_ids["a"], "Backpropagation", "neural-networks")
            graph_repo.ensure_node(kuzu_conn, concept_ids["b"], "Gradient Descent", "neural-networks")
            graph_repo.ensure_node(kuzu_conn, concept_ids["parent"], "Neural Networks", "neural-networks")
            graph_repo.add_relationship(
                kuzu_conn, source_id=concept_ids["a"], target_id=concept_ids["parent"],
                type="subtopic-of", justification="attaching synthesized parent", job_id=invocation.job_id,
            )
            graph_repo.add_relationship(
                kuzu_conn, source_id=concept_ids["b"], target_id=concept_ids["parent"],
                type="subtopic-of", justification="attaching synthesized parent", job_id=invocation.job_id,
            )
            payload = {
                "relationships_written": [
                    {"source_id": concept_ids["a"], "target_id": concept_ids["parent"], "type": "subtopic-of", "action": "created"},
                    {"source_id": concept_ids["b"], "target_id": concept_ids["parent"], "type": "subtopic-of", "action": "created"},
                ],
                "structural_gaps": [],
            }
            return EngineResult(is_error=False, result_text="```json\n" + json.dumps(payload) + "\n```", cost_usd=0.01)

        # Both the real Text Agent round and the gap-synthesis round share
        # agent_role == AgentRole.TEXT_AGENT.value (Critical fix: gap
        # synthesis reuses Text Agent's already-seeded AgentConfig row
        # rather than a nonexistent "text_agent_gap_synthesis" role) — they
        # are told apart here by prompt content, exactly as the real
        # Orchestrator has no other distinguishing signal between them at
        # this boundary either.
        assert invocation.agent_role == AgentRole.TEXT_AGENT.value

        if _GAP_SYNTHESIS_PROMPT_MARKER in invocation.prompt:
            gap_synthesis_agent_roles.append(invocation.agent_role)
            text_agent_gap_prompts.append(invocation.prompt)
            async with self._session_factory() as session:
                parent = await concept_repo.create_concept(
                    session, title="Neural Networks", category="neural-networks",
                    body="Synthesized explanation of neural networks, grounding both children.",
                    metadata={"origin": "gap_synthesis", "gap_member_ids": [concept_ids["a"], concept_ids["b"]]},
                    job_id=invocation.job_id,
                )
            concept_ids["parent"] = parent.id
            payload = {"concept_written": {"concept_id": parent.id, "title": "Neural Networks", "action": "created"}}
            return EngineResult(is_error=False, result_text="```json\n" + json.dumps(payload) + "\n```", cost_usd=0.015)

        async with self._session_factory() as session:
            concept_a = await concept_repo.create_concept(
                session, title="Backpropagation", category="neural-networks",
                body="Body text about backpropagation.", metadata={}, job_id=invocation.job_id,
            )
            concept_b = await concept_repo.create_concept(
                session, title="Gradient Descent", category="neural-networks",
                body="Body text about gradient descent.", metadata={}, job_id=invocation.job_id,
            )
        concept_ids["a"] = concept_a.id
        concept_ids["b"] = concept_b.id
        structured_output = {
            "segmentation": [
                {"title": "Backpropagation", "scope_description": "Backprop only.", "source_excerpt_ref": "p1"},
                {"title": "Gradient Descent", "scope_description": "GD only.", "source_excerpt_ref": "p2"},
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

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    compiled = build_graph(session_factory, kuzu_conn)
    final_state = await compiled.ainvoke(_initial_state(job, source))

    assert final_state["status"] == "succeeded"
    assert final_state["synthesized_node_count"] == 1
    assert "concept-1" not in text_agent_gap_prompts[0]  # sanity: real ids were interpolated, not placeholders
    assert concept_ids["a"] in text_agent_gap_prompts[0]
    assert concept_ids["b"] in text_agent_gap_prompts[0]

    # Fix 1a: the newly-synthesized concept's id must be tracked on state so
    # Validation Agent's prompt can carry its looser grounding rule.
    assert final_state["synthesized_concept_ids"] == [concept_ids["parent"]]

    # Critical fix regression coverage: the engine invocation for the
    # gap-synthesis round must carry Text Agent's own agent_role (there is
    # no separate "text_agent_gap_synthesis" AgentRole/AgentConfig), while
    # the job_round trace label below stays "text_agent_gap_synthesis" —
    # these are two distinct fields and must not be conflated.
    assert gap_synthesis_agent_roles == [AgentRole.TEXT_AGENT.value]

    parent = await concept_repo.get_concept(db_session, concept_ids["parent"])
    assert parent.status == "committed"
    assert parent.metadata_["origin"] == "gap_synthesis"

    relationships = graph_repo.search_relationships(kuzu_conn, concept_ids["a"])
    assert any(
        r.target_id == concept_ids["parent"] and r.type == "subtopic-of" and r.status == "committed"
        for r in relationships
    )

    round_result = await db_session.execute(
        select(JobRound).where(JobRound.job_id == job.id).order_by(JobRound.round_number)
    )
    agent_types = [r.agent_type for r in round_result.scalars().all()]
    assert agent_types == [
        "text_agent", "graph_agent", "text_agent_gap_synthesis", "graph_agent", "validation_agent",
    ]


@pytest.mark.asyncio
async def test_structural_gap_cap_hit_degrades_gracefully_and_commits(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    """synthesized_node_count starts already at the cap — the flagged gap
    must be ignored (no invoke_text_agent_for_gap call at all) and the job
    must still commit normally (spec §4: cap-hit is not a failure)."""
    job, source = await _make_job_and_source(db_session)
    gap_node_calls = {"count": 0}

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "validation_agent":
            return EngineResult(is_error=False, result_text=_PASS_VALIDATION_RESULT_TEXT, cost_usd=0.0)
        if invocation.agent_role == "graph_agent":
            return EngineResult(
                is_error=False,
                result_text=_gap_flagging_relationships_output(["concept-1", "concept-2"]),
                cost_usd=0.01,
            )
        # Gap synthesis reuses agent_role == AgentRole.TEXT_AGENT.value (no
        # separate "text_agent_gap_synthesis" role exists), so the tripwire
        # for "gap synthesis must not run" has to key off prompt content,
        # not agent_role, to still catch a regression here.
        assert invocation.agent_role == AgentRole.TEXT_AGENT.value
        if _GAP_SYNTHESIS_PROMPT_MARKER in invocation.prompt:
            gap_node_calls["count"] += 1
            pytest.fail("gap synthesis must not run once the cap is already hit")
        async with self._session_factory() as session:
            await concept_repo.create_concept(
                session, title="Concept A", category="general", body="Body A.",
                metadata={}, job_id=invocation.job_id,
            )
        return EngineResult(is_error=False, result_text=_success_result_text("concept-1", "concept-2"), cost_usd=0.02)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    compiled = build_graph(session_factory, kuzu_conn)
    initial_state = {**_initial_state(job, source), "synthesized_node_count": MAX_SYNTHESIZED_NODES}
    final_state = await compiled.ainvoke(initial_state)

    assert final_state["status"] == "succeeded"
    assert gap_node_calls["count"] == 0
    assert final_state["synthesized_node_count"] == MAX_SYNTHESIZED_NODES


# --- Final-review fix wave (2026-09-27) ---


@pytest.mark.asyncio
async def test_graph_agent_relationships_accumulate_across_gap_resume_rounds(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    """Fix 1b: invoke_graph_agent must ACCUMULATE relationships_written
    across rounds within a job rather than replacing it wholesale — a real
    edge proposed in the gap-flagging round must still be visible to
    Validation Agent alongside the resume round's edges, not silently
    dropped from what the validator sees (though it stayed staged in Kùzu
    and would otherwise get committed unreviewed)."""
    job, source = await _make_job_and_source(db_session)
    concept_ids: dict[str, str] = {}
    graph_agent_calls = {"count": 0}
    validation_prompts: list[str] = []

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "validation_agent":
            validation_prompts.append(invocation.prompt)
            return EngineResult(is_error=False, result_text=_PASS_VALIDATION_RESULT_TEXT, cost_usd=0.0)

        if invocation.agent_role == "graph_agent":
            graph_agent_calls["count"] += 1
            if graph_agent_calls["count"] == 1:
                # Round 1: propose one real edge between the two siblings
                # AND flag the missing-parent gap in the same round.
                graph_repo.ensure_node(kuzu_conn, concept_ids["a"], "Backpropagation", "neural-networks")
                graph_repo.ensure_node(kuzu_conn, concept_ids["b"], "Gradient Descent", "neural-networks")
                graph_repo.add_relationship(
                    kuzu_conn, source_id=concept_ids["a"], target_id=concept_ids["b"],
                    type="related-to", justification="round 1 sibling relation", job_id=invocation.job_id,
                )
                payload = {
                    "relationships_written": [
                        {"source_id": concept_ids["a"], "target_id": concept_ids["b"], "type": "related-to", "action": "created"}
                    ],
                    "structural_gaps": [
                        {
                            "gap_type": "missing_parent",
                            "member_concept_ids": [concept_ids["a"], concept_ids["b"]],
                            "proposed_title": "Neural Networks",
                            "proposed_scope_hint": "The umbrella topic covering both members.",
                            "justification": f"{concept_ids['a']} and {concept_ids['b']} share no common ancestor within 2 hops.",
                        }
                    ],
                }
                return EngineResult(is_error=False, result_text="```json\n" + json.dumps(payload) + "\n```", cost_usd=0.01)

            # Round 2 (resume): attach the two siblings to the newly
            # synthesized parent.
            graph_repo.ensure_node(kuzu_conn, concept_ids["parent"], "Neural Networks", "neural-networks")
            graph_repo.add_relationship(
                kuzu_conn, source_id=concept_ids["a"], target_id=concept_ids["parent"],
                type="subtopic-of", justification="attaching synthesized parent", job_id=invocation.job_id,
            )
            graph_repo.add_relationship(
                kuzu_conn, source_id=concept_ids["b"], target_id=concept_ids["parent"],
                type="subtopic-of", justification="attaching synthesized parent", job_id=invocation.job_id,
            )
            payload = {
                "relationships_written": [
                    {"source_id": concept_ids["a"], "target_id": concept_ids["parent"], "type": "subtopic-of", "action": "created"},
                    {"source_id": concept_ids["b"], "target_id": concept_ids["parent"], "type": "subtopic-of", "action": "created"},
                ],
                "structural_gaps": [],
            }
            return EngineResult(is_error=False, result_text="```json\n" + json.dumps(payload) + "\n```", cost_usd=0.01)

        assert invocation.agent_role == AgentRole.TEXT_AGENT.value
        if _GAP_SYNTHESIS_PROMPT_MARKER in invocation.prompt:
            async with self._session_factory() as session:
                parent = await concept_repo.create_concept(
                    session, title="Neural Networks", category="neural-networks",
                    body="Synthesized explanation of neural networks, grounding both children.",
                    metadata={"origin": "gap_synthesis", "gap_member_ids": [concept_ids["a"], concept_ids["b"]]},
                    job_id=invocation.job_id,
                )
            concept_ids["parent"] = parent.id
            payload = {"concept_written": {"concept_id": parent.id, "title": "Neural Networks", "action": "created"}}
            return EngineResult(is_error=False, result_text="```json\n" + json.dumps(payload) + "\n```", cost_usd=0.015)

        async with self._session_factory() as session:
            concept_a = await concept_repo.create_concept(
                session, title="Backpropagation", category="neural-networks",
                body="Body text about backpropagation.", metadata={}, job_id=invocation.job_id,
            )
            concept_b = await concept_repo.create_concept(
                session, title="Gradient Descent", category="neural-networks",
                body="Body text about gradient descent.", metadata={}, job_id=invocation.job_id,
            )
        concept_ids["a"] = concept_a.id
        concept_ids["b"] = concept_b.id
        structured_output = {
            "segmentation": [
                {"title": "Backpropagation", "scope_description": "Backprop only.", "source_excerpt_ref": "p1"},
                {"title": "Gradient Descent", "scope_description": "GD only.", "source_excerpt_ref": "p2"},
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

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    compiled = build_graph(session_factory, kuzu_conn)
    final_state = await compiled.ainvoke(_initial_state(job, source))

    assert final_state["status"] == "succeeded"
    assert len(validation_prompts) == 1
    # Round 1's edge (related-to) and round 2's two edges (subtopic-of) must
    # BOTH be visible to Validation Agent — not just the latest round's.
    assert "related-to" in validation_prompts[0]
    assert "subtopic-of" in validation_prompts[0]
    assert final_state["graph_agent_result"]["relationships_written"] == [
        {"source_id": concept_ids["a"], "target_id": concept_ids["b"], "type": "related-to", "action": "created"},
        {"source_id": concept_ids["a"], "target_id": concept_ids["parent"], "type": "subtopic-of", "action": "created"},
        {"source_id": concept_ids["b"], "target_id": concept_ids["parent"], "type": "subtopic-of", "action": "created"},
    ]

    # Fix 4: structural_gaps must show up in the graph_agent job_round trace.
    round_result = await db_session.execute(
        select(JobRound).where(JobRound.job_id == job.id, JobRound.agent_type == "graph_agent").order_by(JobRound.round_number)
    )
    graph_rounds = round_result.scalars().all()
    assert len(graph_rounds) == 2
    assert graph_rounds[0].structured_output_json["structural_gaps"][0]["gap_type"] == "missing_parent"
    assert graph_rounds[1].structured_output_json["structural_gaps"] == []


@pytest.mark.asyncio
async def test_malformed_structural_gap_entry_routes_to_rollback_as_failed(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    """Fix 2: a malformed structural_gaps entry (missing a required key, or
    a gap_type other than 'missing_parent') must raise
    GraphAgentOutputParseError from parse_output rather than crash
    uncaught, and the job must correctly route to rollback (status becomes
    'failed', all pending rows removed) — this is the gap-node
    parse-failure test the plan claimed existed but didn't."""
    job, source = await _make_job_and_source(db_session)

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "graph_agent":
            malformed_payload = {
                "relationships_written": [],
                "structural_gaps": [
                    {
                        "gap_type": "missing_child",  # unsupported per spec §3
                        "member_concept_ids": ["concept-1", "concept-2"],
                        "proposed_title": "Neural Networks",
                        "proposed_scope_hint": "hint",
                        "justification": "justification",
                    }
                ],
            }
            return EngineResult(
                is_error=False,
                result_text="```json\n" + json.dumps(malformed_payload) + "\n```",
                cost_usd=0.01,
            )
        assert invocation.agent_role == "text_agent"
        async with self._session_factory() as session:
            await concept_repo.create_concept(
                session, title="Concept A", category="general", body="Body A.",
                metadata={}, job_id=invocation.job_id,
            )
        return EngineResult(is_error=False, result_text=_success_result_text("concept-1", "concept-2"), cost_usd=0.02)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    compiled = build_graph(session_factory, kuzu_conn)
    final_state = await compiled.ainvoke(_initial_state(job, source))

    assert final_state["status"] == "failed"
    assert "missing_child" in final_state["error"] or "missing_parent" in final_state["error"]

    result = await db_session.execute(select(Concept).where(Concept.job_id == job.id))
    assert result.scalars().all() == []


@pytest.mark.asyncio
async def test_validation_reject_on_two_gap_synthesized_concepts_reworks_both(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    """Fix 3: a reject round flagging two DISTINCT gap-synthesized concepts
    must rework both, not just the first — two text_agent_gap_synthesis
    job_rounds in that resume, both concepts' bodies updated."""
    job, source = await _make_job_and_source(db_session)
    concept_one = await concept_repo.create_concept(
        db_session, title="Neural Networks", category="general", body="wrong body one",
        metadata={"origin": "gap_synthesis", "gap_member_ids": ["a", "b"]}, job_id=job.id,
    )
    concept_two = await concept_repo.create_concept(
        db_session, title="Optimization", category="general", body="wrong body two",
        metadata={"origin": "gap_synthesis", "gap_member_ids": ["c", "d"]}, job_id=job.id,
    )
    await db_session.commit()
    validation_calls = {"count": 0}
    rework_prompts: list[str] = []
    issues = [
        {
            "category": "ungrounded_content",
            "severity": "high",
            "target_id": concept_one.id,
            "description": "concept one invents a fact",
        },
        {
            "category": "ungrounded_content",
            "severity": "high",
            "target_id": concept_two.id,
            "description": "concept two invents a different fact",
        },
    ]

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "validation_agent":
            validation_calls["count"] += 1
            if validation_calls["count"] == 1:
                return EngineResult(is_error=False, result_text=_reject_validation_result_text(issues), cost_usd=0.0)
            return EngineResult(is_error=False, result_text=_PASS_VALIDATION_RESULT_TEXT, cost_usd=0.0)
        if invocation.agent_role == "graph_agent":
            return EngineResult(is_error=False, result_text=_no_gap_relationships_output(), cost_usd=0.0)
        assert invocation.agent_role == AgentRole.TEXT_AGENT.value
        if _GAP_REWORK_PROMPT_MARKER in invocation.prompt:
            rework_prompts.append(invocation.prompt)
            if concept_one.id in invocation.prompt:
                target, new_body = concept_one, "repaired-body-one"
            else:
                assert concept_two.id in invocation.prompt
                target, new_body = concept_two, "repaired-body-two"
            async with self._session_factory() as session:
                await concept_repo.update_concept(
                    session, concept_id=target.id, job_id=invocation.job_id,
                    body=new_body, metadata={"origin": "gap_synthesis"},
                )
            payload = {"concept_written": {"concept_id": target.id, "title": target.title, "action": "updated"}}
            return EngineResult(is_error=False, result_text="```json\n" + json.dumps(payload) + "\n```", cost_usd=0.01)
        return EngineResult(is_error=False, result_text=_no_op_text_agent_result_text(), cost_usd=0.01)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    compiled = build_graph(session_factory, kuzu_conn)
    final_state = await compiled.ainvoke(_initial_state(job, source))

    assert final_state["status"] == "succeeded"
    assert len(rework_prompts) == 2  # both flagged concepts got their own rework invocation

    reworked_one = await concept_repo.get_concept(db_session, concept_one.id)
    reworked_two = await concept_repo.get_concept(db_session, concept_two.id)
    assert reworked_one.body == "repaired-body-one"
    assert reworked_two.body == "repaired-body-two"

    round_result = await db_session.execute(
        select(JobRound).where(JobRound.job_id == job.id, JobRound.agent_type == "text_agent_gap_synthesis")
        .order_by(JobRound.round_number)
    )
    gap_rounds = round_result.scalars().all()
    assert len(gap_rounds) == 2


# --- Task 6: origin-aware critique routing for gap-synthesized concepts ---


def _no_gap_relationships_output() -> str:
    return '```json\n{"relationships_written": []}\n```'


# Distinguishes a rework-mode gap-synthesis invocation from a normal Text
# Agent round by prompt content, same pattern as
# `_GAP_SYNTHESIS_PROMPT_MARKER` above — both share
# `agent_role == AgentRole.TEXT_AGENT.value` (no separate
# "text_agent_gap_synthesis" AgentRole/AgentConfig exists), so agent_role
# alone can't tell them apart.
_GAP_REWORK_PROMPT_MARKER = "invoked to rework a concept"


@pytest.mark.asyncio
async def test_validation_reject_on_gap_synthesized_concept_routes_to_rework(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    job, source = await _make_job_and_source(db_session)
    gap_concept = await concept_repo.create_concept(
        db_session, title="Neural Networks", category="general", body="wrong body",
        metadata={"origin": "gap_synthesis", "gap_member_ids": ["a", "b"]}, job_id=job.id,
    )
    await db_session.commit()
    validation_calls = {"count": 0}
    gap_synthesis_prompts: list[str] = []
    issue = {
        "category": "ungrounded_content",
        "severity": "high",
        "target_id": gap_concept.id,
        "description": "invents a fact the members don't support",
    }

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "validation_agent":
            validation_calls["count"] += 1
            if validation_calls["count"] == 1:
                return EngineResult(is_error=False, result_text=_reject_validation_result_text([issue]), cost_usd=0.0)
            return EngineResult(is_error=False, result_text=_PASS_VALIDATION_RESULT_TEXT, cost_usd=0.0)
        if invocation.agent_role == "graph_agent":
            return EngineResult(is_error=False, result_text=_no_gap_relationships_output(), cost_usd=0.0)
        # Both the initial Text Agent round and the gap-rework round share
        # agent_role == AgentRole.TEXT_AGENT.value — told apart here by
        # prompt content, same as the real Orchestrator has no other
        # distinguishing signal between them at this boundary either.
        assert invocation.agent_role == AgentRole.TEXT_AGENT.value
        if _GAP_REWORK_PROMPT_MARKER in invocation.prompt:
            gap_synthesis_prompts.append(invocation.prompt)
            async with self._session_factory() as session:
                await concept_repo.update_concept(
                    session, concept_id=gap_concept.id, job_id=invocation.job_id,
                    body="repaired-body-xyz", metadata={"origin": "gap_synthesis", "gap_member_ids": ["a", "b"]},
                )
            payload = {"concept_written": {"concept_id": gap_concept.id, "title": "Neural Networks", "action": "updated"}}
            return EngineResult(is_error=False, result_text="```json\n" + json.dumps(payload) + "\n```", cost_usd=0.01)
        return EngineResult(is_error=False, result_text=_no_op_text_agent_result_text(), cost_usd=0.01)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    compiled = build_graph(session_factory, kuzu_conn)
    # `gap_concept` already exists in the DB with `origin: gap_synthesis` before
    # the job starts; the job's own first Text/Graph Agent rounds don't touch
    # it (they're no-ops here), so the first Validation Agent round rejects
    # against it and this test asserts the rejection is routed to rework.
    final_state = await compiled.ainvoke(_initial_state(job, source))

    assert final_state["status"] == "succeeded"
    assert len(gap_synthesis_prompts) == 1
    # Sanity: the prompt is built (and the engine invoked) before the fake
    # engine's fix is applied, so it can never contain the fix's own literal
    # content — using a body string distinct from the real prompt template's
    # own static wording (which itself says "...update_concept with the
    # corrected body...") so this check isn't a false positive against that
    # boilerplate.
    assert "repaired-body-xyz" not in gap_synthesis_prompts[0]
    assert "invents a fact" in gap_synthesis_prompts[0]
    assert gap_concept.id in gap_synthesis_prompts[0]

    reworked = await concept_repo.get_concept(db_session, gap_concept.id)
    assert reworked.body == "repaired-body-xyz"
    assert reworked.metadata_["origin"] == "gap_synthesis"  # not wiped by the rework


@pytest.mark.asyncio
async def test_validation_reject_on_mixed_origin_targets_falls_back_to_normal_text_agent(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    job, source = await _make_job_and_source(db_session)
    gap_concept = await concept_repo.create_concept(
        db_session, title="Neural Networks", category="general", body="body",
        metadata={"origin": "gap_synthesis"}, job_id=job.id,
    )
    normal_concept = await concept_repo.create_concept(
        db_session, title="Backpropagation", category="general", body="body",
        metadata={}, job_id=job.id,
    )
    await db_session.commit()
    validation_calls = {"count": 0}
    text_agent_calls = {"count": 0}
    gap_synthesis_calls = {"count": 0}
    issues = [
        {"category": "ungrounded_content", "severity": "high", "target_id": gap_concept.id, "description": "d1"},
        {"category": "ungrounded_content", "severity": "high", "target_id": normal_concept.id, "description": "d2"},
    ]

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "validation_agent":
            validation_calls["count"] += 1
            if validation_calls["count"] == 1:
                return EngineResult(is_error=False, result_text=_reject_validation_result_text(issues), cost_usd=0.0)
            return EngineResult(is_error=False, result_text=_PASS_VALIDATION_RESULT_TEXT, cost_usd=0.0)
        if invocation.agent_role == "graph_agent":
            return EngineResult(is_error=False, result_text=_no_gap_relationships_output(), cost_usd=0.0)
        assert invocation.agent_role == AgentRole.TEXT_AGENT.value
        if _GAP_REWORK_PROMPT_MARKER in invocation.prompt:
            gap_synthesis_calls["count"] += 1
            pytest.fail("mixed-origin rejection must fall back to the normal text_agent path")
        text_agent_calls["count"] += 1
        return EngineResult(is_error=False, result_text=_no_op_text_agent_result_text(), cost_usd=0.01)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    compiled = build_graph(session_factory, kuzu_conn)
    final_state = await compiled.ainvoke(_initial_state(job, source))

    assert final_state["status"] == "succeeded"
    assert gap_synthesis_calls["count"] == 0
    assert text_agent_calls["count"] == 2  # initial round + one normal-path retry


@pytest.mark.asyncio
async def test_validation_reject_with_gap_rework_and_graph_agent_issue_preserves_graph_delta(
    db_session: AsyncSession, session_factory, kuzu_conn: kuzu.Connection, monkeypatch
):
    """Regression coverage: invoke_validation_agent can populate BOTH
    gap_rework_target_concept_ids (all text_agent-categorized issues target a
    gap-synthesized concept) AND graph_agent_critique_delta (a separate
    graph_agent-categorized issue) in the SAME reject round — these two are
    independent, not mutually exclusive. _route_after_validation_agent picks
    the rework path first, so invoke_text_agent_for_gap's rework branch runs
    before invoke_graph_agent's resumed round — its return must not wipe the
    graph_agent_critique_delta that invoke_validation_agent already set."""
    job, source = await _make_job_and_source(db_session)
    gap_concept = await concept_repo.create_concept(
        db_session, title="Neural Networks", category="general", body="wrong body",
        metadata={"origin": "gap_synthesis", "gap_member_ids": ["a", "b"]}, job_id=job.id,
    )
    await db_session.commit()
    validation_calls = {"count": 0}
    graph_agent_prompts: list[str] = []
    text_issue = {
        "category": "ungrounded_content",
        "severity": "high",
        "target_id": gap_concept.id,
        "description": "invents a fact the members don't support",
    }
    graph_issue = {
        "category": "unsupported_justification",
        "severity": "high",
        "target_id": "edge-1",
        "description": "the justification doesn't establish the claim",
    }

    async def fake_invoke(self, invocation):
        if invocation.agent_role == "validation_agent":
            validation_calls["count"] += 1
            if validation_calls["count"] == 1:
                return EngineResult(
                    is_error=False,
                    result_text=_reject_validation_result_text([text_issue, graph_issue]),
                    cost_usd=0.0,
                )
            return EngineResult(is_error=False, result_text=_PASS_VALIDATION_RESULT_TEXT, cost_usd=0.0)
        if invocation.agent_role == "graph_agent":
            graph_agent_prompts.append(invocation.prompt)
            return EngineResult(is_error=False, result_text=_no_gap_relationships_output(), cost_usd=0.0)
        assert invocation.agent_role == AgentRole.TEXT_AGENT.value
        if _GAP_REWORK_PROMPT_MARKER in invocation.prompt:
            async with self._session_factory() as session:
                await concept_repo.update_concept(
                    session, concept_id=gap_concept.id, job_id=invocation.job_id,
                    body="repaired-body-xyz", metadata={"origin": "gap_synthesis", "gap_member_ids": ["a", "b"]},
                )
            payload = {"concept_written": {"concept_id": gap_concept.id, "title": "Neural Networks", "action": "updated"}}
            return EngineResult(is_error=False, result_text="```json\n" + json.dumps(payload) + "\n```", cost_usd=0.01)
        return EngineResult(is_error=False, result_text=_no_op_text_agent_result_text(), cost_usd=0.01)

    monkeypatch.setattr(ClaudeCodeEngine, "invoke", fake_invoke)

    compiled = build_graph(session_factory, kuzu_conn)
    final_state = await compiled.ainvoke(_initial_state(job, source))

    assert final_state["status"] == "succeeded"
    # The graph_agent_critique_delta from round 1's rejection must have
    # survived the rework branch's return (which only clears its own
    # gap_rework_* fields) and reached invoke_graph_agent's resumed-round
    # prompt.
    assert len(graph_agent_prompts) == 1
    assert "unsupported_justification" in graph_agent_prompts[0]
    assert "edge-1" in graph_agent_prompts[0]
    assert final_state.get("graph_agent_critique_delta") is None  # cleared normally by invoke_graph_agent's own success path

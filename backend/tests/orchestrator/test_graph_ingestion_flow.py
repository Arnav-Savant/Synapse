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

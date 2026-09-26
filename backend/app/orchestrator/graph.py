"""The Phase 4 ingestion graph: assess signals -> invoke the Text Agent ->
commit or roll back (spec §6.4/§8 of
docs/superpowers/specs/2026-09-24-multi-agent-architecture-design.md).

`build_graph(session_factory, kuzu_conn)` returns a compiled LangGraph
`CompiledStateGraph` over `OrchestratorState`. Node functions are closures
over `session_factory`/`kuzu_conn`/a `ClaudeCodeEngine` instance, matching
the resource-injection idiom `mcp_server/server.py`'s `SynapseMcpServer`
already uses (an async-context-manager factory closed over rather than
threaded through LangGraph's `RunnableConfig`) — the node function signature
LangGraph invokes is `(state) -> state`, same shape proven in
`tests/orchestrator/test_state_graph_smoke.py`.

Phase 5 (Graph Agent) has landed: `invoke_text_agent` produces
`should_run_graph_agent` from the real Text Agent output, and
`invoke_graph_agent` is routed to whenever it's True, extending this graph
without restructuring it as originally planned.
"""

import logging
from dataclasses import asdict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents import graph_agent
from app.agents.graph_agent import GraphAgentOutputParseError
from app.agents.text_agent import TextAgentOutputParseError, build_prompt, parse_output
from app.engines.base import EngineInvocation
from app.engines.claude_code_engine import ClaudeCodeEngine, ClaudeCodeEngineError
from app.mcp_server.server import TOOL_REGISTRY, AgentRole
from app.orchestrator.state import OrchestratorState
from app.orchestrator.tools import (
    SourceSignals,
    commit_job,
    get_source_signals,
    rollback_job,
    should_run_graph_agent,
)
from app.repositories import job_round_repo, source_record_repo
from app.services import graph_service

logger = logging.getLogger(__name__)


def build_graph(session_factory, kuzu_conn) -> CompiledStateGraph:
    """session_factory: an async context manager factory yielding an
    AsyncSession (same idiom as `ClaudeCodeEngine.__init__`/
    `SynapseMcpServer._session_factory`). kuzu_conn: a live `kuzu.Connection`
    for the commit/rollback transactional boundary (`orchestrator/tools.py`).
    """
    engine = ClaudeCodeEngine(session_factory)

    async def assess_signals(state: OrchestratorState) -> OrchestratorState:
        async with session_factory() as session:
            signals = await get_source_signals(session, state["source_id"])
        # Phase 4 has no Graph Agent yet (Phase 5) — always False here;
        # Phase 5 flips this to real logic without restructuring this graph.
        return {**state, "signals": asdict(signals), "should_run_graph_agent": False}

    async def invoke_text_agent(state: OrchestratorState) -> OrchestratorState:
        try:
            async with session_factory() as session:
                source = await source_record_repo.read_source(session, state["source_id"])
            signals = SourceSignals(**state["signals"])
            prompt = build_prompt(source, signals)
            result = await engine.invoke(
                EngineInvocation(
                    agent_role=AgentRole.TEXT_AGENT.value,
                    job_id=state["job_id"],
                    prompt=prompt,
                    tool_names=TOOL_REGISTRY[AgentRole.TEXT_AGENT],
                )
            )
            output = parse_output(result.result_text)

            next_round_number = state["round_number"] + 1
            async with session_factory() as session:
                await job_round_repo.create_job_round(
                    session,
                    job_id=state["job_id"],
                    round_number=next_round_number,
                    agent_type="text_agent",
                    prompt_delta=None,
                    output_summary=result.result_text[:500],
                    structured_output_json={
                        "segmentation": output.segmentation,
                        "overlap_check": output.overlap_check,
                        "concepts_written": output.concepts_written,
                    },
                    cost_usd=result.cost_usd,
                )

            return {
                **state,
                "text_agent_result": asdict(output),
                "round_number": next_round_number,
                "should_run_graph_agent": should_run_graph_agent(output),
            }
        except (ClaudeCodeEngineError, TextAgentOutputParseError) as exc:
            # Never let this propagate out of the node (§14.3: this is
            # exactly the layer that can meaningfully react to the
            # failure) — routed to "rollback" by _route_after_text_agent.
            logger.error(
                "text agent invocation failed: job=%s source=%s error=%s",
                state["job_id"],
                state["source_id"],
                exc,
            )
            return {**state, "status": "failed", "error": str(exc)}

    async def invoke_graph_agent(state: OrchestratorState) -> OrchestratorState:
        try:
            prompt = graph_agent.build_prompt(state["text_agent_result"]["concepts_written"])
            result = await engine.invoke(
                EngineInvocation(
                    agent_role=AgentRole.GRAPH_AGENT.value,
                    job_id=state["job_id"],
                    prompt=prompt,
                    tool_names=TOOL_REGISTRY[AgentRole.GRAPH_AGENT],
                )
            )
            output = graph_agent.parse_output(result.result_text)

            next_round_number = state["round_number"] + 1
            async with session_factory() as session:
                await job_round_repo.create_job_round(
                    session,
                    job_id=state["job_id"],
                    round_number=next_round_number,
                    agent_type="graph_agent",
                    prompt_delta=None,
                    output_summary=result.result_text[:500],
                    structured_output_json={"relationships_written": output.relationships_written},
                    cost_usd=result.cost_usd,
                )

            return {
                **state,
                "graph_agent_result": asdict(output),
                "round_number": next_round_number,
            }
        except (ClaudeCodeEngineError, GraphAgentOutputParseError) as exc:
            # Never let this propagate out of the node (§14.3) — routed to
            # "rollback" by _route_after_graph_agent.
            logger.error(
                "graph agent invocation failed: job=%s source=%s error=%s",
                state["job_id"],
                state["source_id"],
                exc,
            )
            return {**state, "status": "failed", "error": str(exc)}

    async def commit(state: OrchestratorState) -> OrchestratorState:
        async with session_factory() as session:
            await commit_job(session, kuzu_conn, state["job_id"])
        graph_service.invalidate()
        logger.info("job committed via graph: job=%s", state["job_id"])
        return {**state, "status": "succeeded"}

    async def rollback(state: OrchestratorState) -> OrchestratorState:
        async with session_factory() as session:
            await rollback_job(session, kuzu_conn, state["job_id"])
        logger.warning("job rolled back via graph: job=%s error=%s", state["job_id"], state.get("error"))
        # Preserve an already-set failure status/error rather than
        # overwriting it — rollback is reached via either
        # _route_after_text_agent's or _route_after_graph_agent's "failed"
        # branch, so this stays defensive regardless of which node failed.
        return {**state, "status": state.get("status") or "failed"}

    def _route_after_text_agent(state: OrchestratorState) -> str:
        if state.get("status") == "failed":
            return "rollback"
        return "invoke_graph_agent" if state["should_run_graph_agent"] else "commit"

    def _route_after_graph_agent(state: OrchestratorState) -> str:
        return "rollback" if state.get("status") == "failed" else "commit"

    graph = StateGraph(OrchestratorState)
    graph.add_node("assess_signals", assess_signals)
    graph.add_node("invoke_text_agent", invoke_text_agent)
    graph.add_node("invoke_graph_agent", invoke_graph_agent)
    graph.add_node("commit", commit)
    graph.add_node("rollback", rollback)
    graph.add_edge(START, "assess_signals")
    graph.add_edge("assess_signals", "invoke_text_agent")
    graph.add_conditional_edges(
        "invoke_text_agent",
        _route_after_text_agent,
        {"invoke_graph_agent": "invoke_graph_agent", "commit": "commit", "rollback": "rollback"},
    )
    graph.add_conditional_edges(
        "invoke_graph_agent", _route_after_graph_agent, {"commit": "commit", "rollback": "rollback"}
    )
    graph.add_edge("commit", END)
    graph.add_edge("rollback", END)
    return graph.compile(checkpointer=False)

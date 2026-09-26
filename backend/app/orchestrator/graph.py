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

Phase 6 (Validation Agent + retry loop, spec §5.2/§5.3/§8) has landed:
both specialists' success paths now route to `invoke_validation_agent`
instead of straight to `commit`. A "pass" verdict proceeds to commit as
before; a "reject" verdict either re-invokes the responsible specialist(s)
with an additive critique delta, or escalates (rollback + `needs_review`,
per spec §5.2 step 7) on no-progress or hitting the retry cap.
"""

import logging
from dataclasses import asdict

from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.agents import graph_agent, validation_agent
from app.agents.graph_agent import GraphAgentOutputParseError
from app.agents.text_agent import TextAgentOutputParseError, build_prompt, parse_output
from app.agents.validation_agent import target_agent_for_category
from app.engines.base import EngineInvocation
from app.engines.claude_code_engine import ClaudeCodeEngine, ClaudeCodeEngineError
from app.mcp_server.server import TOOL_REGISTRY, AgentRole
from app.orchestrator.state import OrchestratorState
from app.orchestrator.tools import (
    MAX_VALIDATION_RETRIES,
    SourceSignals,
    commit_job,
    get_source_signals,
    has_no_progress,
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
            prompt = build_prompt(source, signals, critique_delta=state.get("text_agent_critique_delta"))
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
                "text_agent_critique_delta": None,
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
            prompt = graph_agent.build_prompt(
                state["text_agent_result"]["concepts_written"],
                critique_delta=state.get("graph_agent_critique_delta"),
            )
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
                "graph_agent_critique_delta": None,
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

    def _format_validation_critique_delta(issues: list[dict]) -> str:
        lines = [
            f"- category={issue['category']!r}, target_id={issue['target_id']!r}: {issue['description']}"
            for issue in issues
        ]
        return (
            "Validation Agent rejected the previous round with the "
            "following issue(s) assigned to you:\n" + "\n".join(lines)
        )

    async def invoke_validation_agent(state: OrchestratorState) -> OrchestratorState:
        try:
            prompt = validation_agent.build_prompt(
                state["text_agent_result"], state.get("graph_agent_result")
            )
            result = await engine.invoke(
                EngineInvocation(
                    agent_role=AgentRole.VALIDATION_AGENT.value,
                    job_id=state["job_id"],
                    prompt=prompt,
                    tool_names=TOOL_REGISTRY[AgentRole.VALIDATION_AGENT],
                )
            )
            output = validation_agent.parse_output(result.result_text)

            if output.verdict not in ("pass", "reject"):
                # parse_output deliberately doesn't validate this itself
                # (backend-lead's ruling this phase) — a bad verdict is a
                # Validation Agent protocol failure, handled by the except
                # branch below exactly like the other two nodes' failures.
                raise ValueError(f"validation agent returned an invalid verdict: {output.verdict!r}")

            if output.verdict == "reject" and not output.issues:
                # A "reject" with no issues contradicts the agent's own
                # prompt contract (spec §5.2 step 5: "re-invokes only the
                # agent responsible for the flagged issue" — there's no
                # flagged issue to attribute rework to here) and, left
                # unchecked, would fall through to a delta-less
                # re-invocation of whichever agent happened to be the
                # routing fallback. Treated as a protocol failure, same as
                # the bad-verdict check above.
                raise ValueError("validation agent returned 'reject' with an empty issues list")

            issues_by_agent: dict[str, list[dict]] = {"text_agent": [], "graph_agent": []}
            for issue in output.issues:
                # target_agent_for_category raises ValueError for an
                # unrecognized category — left to propagate into this same
                # except branch below, same defensive pattern as the bad
                # verdict check above.
                issues_by_agent[target_agent_for_category(issue["category"])].append(issue)

            next_round_number = state["round_number"] + 1
            async with session_factory() as session:
                await job_round_repo.create_job_round(
                    session,
                    job_id=state["job_id"],
                    round_number=next_round_number,
                    agent_type="validation_agent",
                    prompt_delta=None,
                    output_summary=result.result_text[:500],
                    structured_output_json={"verdict": output.verdict, "issues": output.issues},
                    cost_usd=result.cost_usd,
                )

            # The retry-vs-escalate-vs-pass decision (spec §5.2 steps 3-7)
            # is computed here, in the node, rather than in
            # `_route_after_validation_agent` — routing functions in this
            # file are pure `state -> str` reads with no side effects (see
            # every other `_route_after_*`), so any state this decision
            # needs to leave behind (critique deltas, retry_count,
            # prior_validation_issues, an escalated status) has to be set
            # here, where LangGraph actually applies the returned state.
            retry_fields: dict = {}
            if output.verdict == "reject":
                retry_count = state.get("retry_count", 0)
                prior_issues = state.get("prior_validation_issues")
                if has_no_progress(output.issues, prior_issues) or retry_count >= MAX_VALIDATION_RETRIES:
                    # Spec §5.2 step 7: "cap or no-progress -> rollback all
                    # staged writes for this job (§8) and mark the job
                    # needs_review (not silently failed, not silently
                    # committed)". Routed to the existing "rollback" node
                    # below, which preserves this pre-set status instead of
                    # defaulting to "failed".
                    retry_fields["status"] = "needs_review"
                else:
                    if issues_by_agent["text_agent"]:
                        retry_fields["text_agent_critique_delta"] = _format_validation_critique_delta(
                            issues_by_agent["text_agent"]
                        )
                    if issues_by_agent["graph_agent"]:
                        retry_fields["graph_agent_critique_delta"] = _format_validation_critique_delta(
                            issues_by_agent["graph_agent"]
                        )
                    retry_fields["retry_count"] = retry_count + 1
                    retry_fields["prior_validation_issues"] = output.issues

            return {
                **state,
                "validation_result": asdict(output),
                "round_number": next_round_number,
                **retry_fields,
            }
        except (ClaudeCodeEngineError, ValueError) as exc:
            # Never let this propagate out of the node (§14.3) — routed to
            # "rollback" by _route_after_validation_agent. ValueError here
            # covers both a parse failure (ValidationAgentOutputParseError
            # is a ValueError subclass) and this node's own verdict/category
            # validation obligations above.
            logger.error(
                "validation agent invocation failed: job=%s source=%s error=%s",
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
        # Phase 6: the success path now goes to validation instead of
        # straight to commit (spec §5.2 step 1) — Graph Agent still runs
        # first when warranted, same should_run_graph_agent judgment as
        # before.
        return "invoke_graph_agent" if state["should_run_graph_agent"] else "invoke_validation_agent"

    def _route_after_graph_agent(state: OrchestratorState) -> str:
        return "rollback" if state.get("status") == "failed" else "invoke_validation_agent"

    def _route_after_validation_agent(state: OrchestratorState) -> str:
        if state.get("status") in ("failed", "needs_review"):
            return "rollback"
        if state["validation_result"]["verdict"] == "pass":
            return "commit"
        # verdict == "reject", with real progress and retries remaining:
        # invoke_validation_agent already computed which agent(s) need
        # rework and populated the corresponding critique delta(s) — this
        # routing function only reads that decision, per this file's
        # existing pure `state -> str` convention (every other
        # `_route_after_*` above). Prefer Text Agent when it's among the
        # targets: re-running it naturally cascades to Graph Agent
        # afterward via should_run_graph_agent/_route_after_text_agent if
        # concepts changed, so a graph_agent-only delta set alongside a
        # text_agent one is still picked up without a second, separate
        # re-invocation path here.
        return "invoke_text_agent" if state.get("text_agent_critique_delta") else "invoke_graph_agent"

    graph = StateGraph(OrchestratorState)
    graph.add_node("assess_signals", assess_signals)
    graph.add_node("invoke_text_agent", invoke_text_agent)
    graph.add_node("invoke_graph_agent", invoke_graph_agent)
    graph.add_node("invoke_validation_agent", invoke_validation_agent)
    graph.add_node("commit", commit)
    graph.add_node("rollback", rollback)
    graph.add_edge(START, "assess_signals")
    graph.add_edge("assess_signals", "invoke_text_agent")
    graph.add_conditional_edges(
        "invoke_text_agent",
        _route_after_text_agent,
        {
            "invoke_graph_agent": "invoke_graph_agent",
            "invoke_validation_agent": "invoke_validation_agent",
            "rollback": "rollback",
        },
    )
    graph.add_conditional_edges(
        "invoke_graph_agent",
        _route_after_graph_agent,
        {"invoke_validation_agent": "invoke_validation_agent", "rollback": "rollback"},
    )
    graph.add_conditional_edges(
        "invoke_validation_agent",
        _route_after_validation_agent,
        {
            "commit": "commit",
            "rollback": "rollback",
            "invoke_text_agent": "invoke_text_agent",
            "invoke_graph_agent": "invoke_graph_agent",
        },
    )
    graph.add_edge("commit", END)
    graph.add_edge("rollback", END)
    return graph.compile(checkpointer=False)

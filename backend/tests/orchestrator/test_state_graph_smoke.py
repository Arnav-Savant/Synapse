import pytest
from langgraph.graph import StateGraph, START, END

from app.orchestrator.state import OrchestratorState


async def _start_node(state: OrchestratorState) -> OrchestratorState:
    return {**state, "round_number": state["round_number"] + 1}


async def _end_node(state: OrchestratorState) -> OrchestratorState:
    return {**state, "status": "succeeded"}


def _build_smoke_graph():
    graph = StateGraph(OrchestratorState)
    graph.add_node("start_node", _start_node)
    graph.add_node("end_node", _end_node)
    graph.add_edge(START, "start_node")
    graph.add_edge("start_node", "end_node")
    graph.add_edge("end_node", END)
    return graph.compile(checkpointer=False)


@pytest.mark.asyncio
async def test_trivial_graph_ainvoke_round_trips():
    compiled = _build_smoke_graph()
    initial_state: OrchestratorState = {
        "job_id": "job-1", "source_id": "src-1", "signals": None, "text_agent_result": None,
        "should_run_graph_agent": False, "round_number": 0, "status": "running", "error": None,
    }
    result = await compiled.ainvoke(initial_state)
    assert result["round_number"] == 1
    assert result["status"] == "succeeded"

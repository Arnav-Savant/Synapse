from typing import Literal, TypedDict


class OrchestratorState(TypedDict):
    job_id: str
    source_id: str
    signals: dict | None          # will hold a SourceSignals-shaped dict once Task 3 lands (not built yet)
    text_agent_result: dict | None  # will hold a TextAgentOutput-shaped dict once Task 4 lands (not built yet)
    graph_agent_result: dict | None  # will hold a GraphAgentOutput-shaped dict once Task 5/7 lands
    should_run_graph_agent: bool
    round_number: int
    status: Literal["running", "succeeded", "failed", "needs_review"]
    error: str | None

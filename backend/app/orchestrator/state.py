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
    validation_result: dict | None  # will hold a ValidationAgentOutput-shaped dict once Task 2 lands
    text_agent_critique_delta: str | None
    graph_agent_critique_delta: str | None
    prior_validation_issues: list[dict] | None  # the raw `issues` list from the last *rejected* validation round, for the next round's no-progress comparison
    retry_count: int

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
    synthesized_node_count: int  # default 0; incremented only in invoke_text_agent_for_gap on a confirmed create (spec §4)
    synthesized_concept_ids: list[str]  # default []; concept_ids created (not reworked) by invoke_text_agent_for_gap's create-mode branch, across the whole job
    gap_rework_target_concept_ids: list[str] | None  # distinct target_ids across this reject round's text_agent-categorized issues, when all target gap-synthesized concepts (at most MAX_SYNTHESIZED_NODES)
    gap_rework_critique_delta: dict[str, str] | None  # target_id -> that target's own formatted critique text (not the other target's)

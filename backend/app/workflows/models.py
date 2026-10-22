"""Names and payload types shared by the workflows, activities and API.

Workflows pass ids and small decisions, never note bodies: drafts, dossiers
and outlines live in Postgres, so Temporal's history stays small.
"""

from collections.abc import Callable
from datetime import timedelta
from typing import Literal

from pydantic import BaseModel, Field, model_validator
from temporalio import workflow
from temporalio.common import RetryPolicy

from app.schemas.outline import Outline

TASK_QUEUE = "synapse-ingest"
ADMISSION_WORKFLOW_ID = "pipeline-admission"

# At most this many pipelines actively execute; a job waiting at a gate has released its slot.
MAX_ACTIVE_PIPELINES = 2
# The admission workflow restarts itself after this many signals so its history stays small.
ADMISSION_CONTINUE_AS_NEW_AFTER = 500


class AdmissionState(BaseModel):
    """What the admission workflow carries across continue-as-new."""

    waiting: list[str] = Field(default_factory=list)  # job workflow ids, FIFO
    active: list[str] = Field(default_factory=list)


async def hold_slot(job_workflow_id: str, granted: Callable[[], bool]) -> None:
    """Called by a job workflow: asks for a pipeline slot and waits until its own
    `slot_granted` signal handler makes `granted()` true. The caller marks the job
    `queued` before calling and `running` after."""
    await workflow.get_external_workflow_handle(ADMISSION_WORKFLOW_ID).signal("acquire", job_workflow_id)
    await workflow.wait_condition(granted)


async def release_slot(job_workflow_id: str) -> None:
    """Gives the slot back, or leaves the queue if it never got one. Harmless to call twice."""
    await workflow.get_external_workflow_handle(ADMISSION_WORKFLOW_ID).signal("release", job_workflow_id)


class OutlineDecision(BaseModel):
    """The owner's answer at Gate 1: `tree` is the outline as they edited it."""

    kind: Literal["approve", "replan"]
    tree: Outline
    feedback: str | None = None


class NodeFeedback(BaseModel):
    """Feedback on one draft at Gate 2. `scope` says how much to regenerate."""

    node_key: str
    domain_slug: str
    scope: Literal["section", "note", "topic"]
    section: str | None = None
    text: str
    re_research: bool = False

    @model_validator(mode="after")
    def _section_scope_names_a_section(self) -> "NodeFeedback":
        if self.scope == "section" and not (self.section or "").strip():
            raise ValueError("feedback with scope 'section' must name the section")
        if not self.text.strip():
            raise ValueError("feedback text must not be empty")
        return self


class DraftDecision(BaseModel):
    kind: Literal["approve", "feedback"]
    approve_node_keys: list[str] | None = None  # None means every draft
    feedback: list[NodeFeedback] = Field(default_factory=list)


class WorkflowStatus(BaseModel):
    step: str
    awaiting_owner: bool


# Activities that call an agent: a heartbeat every few seconds while the `claude` subprocess runs,
# three attempts for infrastructure trouble (timeouts, rate limits), none for output that was already re-asked.
AGENT_HEARTBEAT_TIMEOUT = timedelta(seconds=60)
AGENT_RETRY = RetryPolicy(
    maximum_attempts=3,
    initial_interval=timedelta(seconds=5),
    backoff_coefficient=2.0,
    maximum_interval=timedelta(minutes=2),
    non_retryable_error_types=["AgentOutputError", "JobNotFoundError", "DomainNotFoundError", "ValueError", "TypeError"],
)
# Retry B: at most this many rewrite-and-revalidate rounds before drafts go to the owner flagged.
MAX_QUALITY_ROUNDS = 2
DB_RETRY = RetryPolicy(maximum_attempts=5, initial_interval=timedelta(seconds=1), backoff_coefficient=2.0)


def round_key(node_key: str, domain_slug: str) -> str:
    """Identifies one draft (a node in one domain's vault) in validation rounds."""
    return f"{node_key}|{domain_slug}"


class PlanNode(BaseModel):
    key: str
    title: str
    parent_keys: list[str]
    domains: list[str]
    is_leaf: bool
    height: int  # 0 for a leaf; a parent is one more than its tallest child


class PlanInfo(BaseModel):
    """The approved outline reduced to what the workflow needs to schedule work (no note content)."""

    topic_mode: bool
    max_parallel: int
    nodes: list[PlanNode]

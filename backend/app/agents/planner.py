"""Planner: topic-only mode. A light web scan, then the outline tree."""

import logging

from pydantic import BaseModel, Field, model_validator

from app.agents.prompt_parts import UNTRUSTED_WEB, profile_block, replan_block
from app.agents.runner import RunResult, run_structured
from app.engines.base import AgentEngine
from app.schemas.domains import DomainProfile
from app.schemas.outline import Outline, OutlineNode, validate_outline

logger = logging.getLogger(__name__)

WEB_TOOLS = ("WebSearch", "WebFetch")


class AgentOutlineNode(BaseModel):
    key: str = Field(description="short unique id such as n1, n2")
    title: str
    summary: str = Field(description="one line saying what the note covers")
    parent_keys: list[str] = Field(default_factory=list, description="keys of its parent node(s); empty only for the single root")
    content_slice: str | None = Field(default=None, description="only when told to: the part of the supplied content for this node")


class AgentOutline(BaseModel):
    """What the Planner/Structurer return. Structural problems become validation
    errors, which `run_structured` feeds back to the agent (Retry A)."""

    topic_title: str
    nodes: list[AgentOutlineNode]

    @model_validator(mode="after")
    def _structure_is_valid(self) -> "AgentOutline":
        problems = validate_outline(self.to_outline())
        if problems:
            raise ValueError("; ".join(problems))
        return self

    def to_outline(self) -> Outline:
        return Outline(
            topic_title=self.topic_title,
            nodes=[OutlineNode(**n.model_dump()) for n in self.nodes],
        )


SIZE_AND_SCOPE_RULES = (
    "Outline rules:\n"
    "- Exactly one root node (no parent): the topic's overview. Every other node has at least one parent.\n"
    "- Size follows the topic: from a single node up to about ten nodes besides the root. Deeper levels only where the topic "
    "truly has them (for example Isolation levels -> Anomalies -> Dirty reads). This is a set of notes, not a book.\n"
    "- Respect the scope rules: adjacent technologies and ecosystems are mention-only and never get their own node.\n"
    "- At most 4 levels deep (the root is level 1) and at most 40 nodes. Prefer a wide, shallow tree.\n"
    "- Titles are unique, plain, and usable as file names (no / \\ : * ? \" < > | # ^ [ ]).\n"
    "- Give every node a one-line `summary`."
)


async def plan_outline(
    engine: AgentEngine,
    *,
    job_id: str,
    topic: str,
    profiles: list[tuple[str, DomainProfile]],
    feedback: str | None = None,
    prior: Outline | None = None,
    max_searches: int = 5,
) -> RunResult[AgentOutline]:
    """`profiles` is one (domain name, profile) per target domain; several only for a cross-domain topic."""
    prompt = (
        "You plan the structure of a set of study notes about a topic the owner may know nothing about.\n\n"
        f"Topic: {topic.strip()}\n\n{profile_block(profiles)}\n\n"
        f"First do a LIGHT web scan, at most {max_searches} searches or fetches in total, only to learn the "
        "landscape of the topic so the outline has the right subtopics. Do not research details; that happens "
        f"later, after the owner approves the outline. {UNTRUSTED_WEB}\n\n"
        f"{SIZE_AND_SCOPE_RULES}\n"
        "Leave `content_slice` out.\n"
    )
    revise = replan_block(prior, feedback)
    if revise:
        prompt += f"\n{revise}\n"
    result = await run_structured(
        engine, role="planner", job_id=job_id, prompt=prompt, model_cls=AgentOutline, tools=WEB_TOOLS, timeout_seconds=600
    )
    logger.info("job %s: planner proposed %d node(s) for %r", job_id[:8], len(result.value.nodes), topic.strip()[:60])
    return result

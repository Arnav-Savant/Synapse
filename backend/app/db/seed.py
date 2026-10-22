import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import ServerConfig
from app.db.models import AgentConfig
from app.repositories import domain_repo
from app.schemas.domains import DomainProfile
from app.services import domain_service

logger = logging.getLogger(__name__)

# role -> (model, effort, params)
_DEFAULTS: dict[str, tuple[str, str, dict]] = {
    "classifier": ("claude-haiku-5-5", "low", {}),
    "planner": ("claude-sonnet-5-5", "medium", {"max_searches": 5}),
    "structurer": ("claude-sonnet-5-5", "medium", {}),
    "researcher": (
        "claude-sonnet-5-5",
        "medium",
        {"max_turns": 12, "max_searches": 8, "timeout_seconds": 600},
    ),
    "placer": ("claude-sonnet-5-5", "low", {}),
    "linker": ("claude-sonnet-5-5", "low", {}),
    "writer": ("claude-opus-5-5", "high", {}),
    "synthesizer": ("claude-sonnet-5-5", "medium", {}),
    "reference_finder": ("claude-haiku-5-5", "low", {}),
    "validator": ("claude-sonnet-5-5", "high", {}),
    "profile_builder": ("claude-sonnet-5-5", "medium", {}),
}


async def seed_default_agent_configs(session: AsyncSession) -> None:
    result = await session.execute(select(AgentConfig.agent_role))
    existing = {row[0] for row in result.all()}
    added: list[str] = []
    for role, (model, effort, params) in _DEFAULTS.items():
        if role in existing:
            continue
        session.add(AgentConfig(agent_role=role, model=model, effort=effort, params=params))
        added.append(role)
        logger.debug("seeding agent config: role=%s model=%s effort=%s", role, model, effort)
    await session.commit()
    if added:
        logger.info("seeded %d default agent configs: %s", len(added), ", ".join(added))


_SYSTEM_DESIGN_PROFILE = DomainProfile(
    objective=(
        "Deep, interview-ready understanding of backend engineering and system design for a backend "
        "software engineer. Explain mechanisms, not just definitions: why things work, trade-offs, and "
        "behaviour under realistic production conditions. Build the ability to reason about systems "
        "independently."
    ),
    depth_sections=[
        "Foundations: what it is, the problem it solves and why that problem exists, assumptions, simple example",
        "Internal mechanisms: how it works step by step, components, data and control flow, relevant "
        "algorithms/data structures/protocols, what happens beneath the abstraction",
        "Engineering application: where and why it is used, how to decide, alternatives and when each wins",
        "Trade-offs and limitations: performance, latency, throughput, consistency, durability, concurrency, "
        "complexity, cost, scalability, when it is the wrong choice",
        "Production behaviour: failure and recovery, race conditions, behaviour under load, partial failures, "
        "observability, consequences of misconfiguration",
        "Advanced internals and connections: edge cases, non-obvious behaviour, links to prerequisite and "
        "adjacent concepts",
    ],
    scope_include=(
        "The topic's own subtopics and the prerequisites needed to understand them (for 'DB isolation "
        "levels': read uncommitted, read committed, repeatable read, serializable, dirty reads, "
        "non-repeatable reads, phantom reads, and similar). Distinguish general principles from "
        "technology-specific behaviour; flag uncertainty that depends on version, configuration or workload. "
        "Size follows the topic: from one note to about ten subtopics."
    ),
    scope_mention_only=(
        "Neighbouring technologies and ecosystems (for example Kafka or Vault when the topic is a database "
        "concept): one line, never their own notes. The result must be notes, not a book."
    ),
    style=(
        "Precise, technically rigorous, professional; concrete examples, step-by-step mechanisms, diagrams "
        "where they materially help; no generic AI-style filler, no praise, no repeated summaries."
    ),
)

# (name, purpose, profile)
_DEFAULT_DOMAINS: list[tuple[str, str, DomainProfile]] = [
    (
        "System Design",
        "Backend engineering and system design: databases, distributed systems, scalability, reliability.",
        _SYSTEM_DESIGN_PROFILE,
    ),
    (
        "DSA",
        "Data structures and algorithms: techniques, complexity analysis, problem patterns.",
        DomainProfile(objective="Understand data structures and algorithms well enough to apply them to new problems."),
    ),
    (
        "AI",
        "Artificial intelligence and machine learning: models, training, retrieval, evaluation, LLM applications.",
        DomainProfile(objective="Understand how AI/ML systems work and how to build and evaluate them."),
    ),
]


async def seed_default_domains(session: AsyncSession, config: ServerConfig) -> None:
    """First run only: seeds the three default domains (and their vault
    folders) when no domain exists yet. Never re-adds one the owner deleted
    while others remain."""
    if await domain_repo.count_domains(session) > 0:
        logger.debug("domains already present, skipping default domain seed")
        return
    logger.info("no domains found, seeding the %d default domains", len(_DEFAULT_DOMAINS))
    for name, purpose, profile in _DEFAULT_DOMAINS:
        await domain_service.create_domain(session, config, name=name, purpose=purpose, profile=profile)

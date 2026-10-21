"""Researcher: topic-only mode, one leaf at a time. Web research into a dossier.

`max_turns` and `max_searches` can only be asked of the agent in the prompt
(the CLI has no turn-limit flag); `timeout_seconds` is enforced by the engine.
"""

import logging

from pydantic import BaseModel

from app.agents.planner import WEB_TOOLS
from app.agents.prompt_parts import UNTRUSTED_WEB, profile_block
from app.agents.runner import RunResult, run_structured
from app.agents.source_check import CheckLive, default_check_live, keep_verified_sources
from app.engines.base import AgentEngine
from app.schemas.dossier import Dossier, Fact, ResearchBudget, Source
from app.schemas.domains import DomainProfile
from app.schemas.outline import OutlineNode

logger = logging.getLogger(__name__)


class AgentDossier(BaseModel):
    facts: list[Fact]
    sources: list[Source]


async def research_node(
    engine: AgentEngine,
    *,
    job_id: str,
    node: OutlineNode,
    topic_title: str,
    profiles: list[tuple[str, DomainProfile]],
    budget: ResearchBudget,
) -> RunResult[Dossier]:
    prompt = (
        "You research one subtopic so a writer can produce an accurate, deep study note from your findings.\n\n"
        f"Overall topic: {topic_title}\nSubtopic to research: {node.title}\nWhat the note covers: {node.summary}\n\n"
        f"{profile_block(profiles)}\n\n"
        "Gather the mechanisms, trade-offs, failure behaviour and concrete examples a deep note needs. You MUST use "
        "the web tools: run WebSearch, then WebFetch the most authoritative pages (official documentation, original "
        "papers, maintainers' write-ups) and base your facts on what you read there. Your own knowledge fills gaps "
        "and adds well-established background, but it is not a substitute for reading sources. Stay on this subtopic: neighbouring technologies are mention-only. "
        "Separate general principles from technology-specific behaviour and say where the answer depends on "
        "version, configuration or workload.\n"
        f"Budget: at most {budget.max_searches} web searches and about {budget.max_turns} turns. Stop as soon as "
        f"you have enough. {UNTRUSTED_WEB}\n\n"
        "Return `facts`: specific, self-contained statements (aim for 10 to 25), each with the `source_urls` that "
        "back it (empty when it is your own knowledge). Return `sources`: only pages you actually opened or that a "
        "search returned, each with title and `kind` (official docs, maintainer/engineering blog, community docs, "
        "or other article)."
    )
    result = await run_structured(
        engine, role="researcher", job_id=job_id, prompt=prompt, model_cls=AgentDossier,
        tools=WEB_TOOLS, timeout_seconds=budget.timeout_seconds,
    )
    if result.fetched_urls == ():
        # The agent skipped the web entirely. Ask once more, firmly, before accepting an unsourced dossier.
        logger.warning("job %s: researcher for %r used no web tools; asking again", job_id[:8], node.title)
        retry = await run_structured(
            engine, role="researcher", job_id=job_id,
            prompt=prompt + "\n\nYour last attempt did not use WebSearch or WebFetch at all. Do so now: search first, then fetch the best pages, then answer.",
            model_cls=AgentDossier, tools=WEB_TOOLS, timeout_seconds=budget.timeout_seconds,
        )
        result = RunResult(value=retry.value, cost_usd=result.cost_usd + retry.cost_usd, fetched_urls=retry.fetched_urls)
        if result.fetched_urls == ():
            logger.warning("job %s: researcher for %r still used no web tools; the dossier has no verified sources", job_id[:8], node.title)
    dossier = Dossier(node_key=node.key, facts=result.value.facts, sources=result.value.sources)
    logger.info("job %s: researched %r: %d fact(s), %d source(s)", job_id[:8], node.title, len(dossier.facts), len(dossier.sources))
    return RunResult(value=dossier, cost_usd=result.cost_usd, fetched_urls=result.fetched_urls)


async def verify_dossier(
    result: RunResult[Dossier], check_live: CheckLive = default_check_live
) -> Dossier:
    """The dossier with only retrieved, live sources; facts keep only the surviving source links."""
    dossier = result.value
    kept = await keep_verified_sources(dossier.sources, result.fetched_urls, check_live)
    kept_urls = {s.url for s in kept}
    facts = [Fact(text=f.text, source_urls=[u for u in f.source_urls if u in kept_urls]) for f in dossier.facts]
    return Dossier(node_key=dossier.node_key, facts=facts, sources=kept)

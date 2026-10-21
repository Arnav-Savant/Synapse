"""Reference finder: ranks and annotates credible links for a note. Both input modes."""

import logging

from app.agents.planner import WEB_TOOLS
from app.agents.prompt_parts import UNTRUSTED_WEB
from app.agents.runner import RunResult, run_structured
from app.agents.source_check import CheckLive, default_check_live, keep_verified_sources
from app.engines.base import AgentEngine
from app.schemas.dossier import KIND_RANK, Dossier, ReferenceList
from app.schemas.outline import OutlineNode

logger = logging.getLogger(__name__)

MAX_REFERENCES = 8


async def find_references(
    engine: AgentEngine,
    *,
    job_id: str,
    node: OutlineNode,
    dossier: Dossier | None,
    check_live: CheckLive = default_check_live,
) -> RunResult[ReferenceList]:
    """With a dossier it starts from that research's sources; without one it searches.
    Only URLs the session retrieved and that are live survive, ordered official >
    maintainer > community > article, at most eight."""
    if dossier is not None and dossier.sources:
        known = "\n".join(f"- {s.title} ({s.kind}): {s.url}" for s in dossier.sources)
        start = f"Research for this note already found these sources:\n{known}\nStart from them and search for more only if they are thin."
    else:
        start = "Search the web for credible sources on this subtopic."
    prompt = (
        "You pick the references listed at the end of a study note.\n\n"
        f"Note: {node.title}\nWhat it covers: {node.summary}\n\n{start}\n\n"
        "Rank by credibility: official documentation first, then maintainers' and engineering blogs, then "
        "community documentation, then other articles. Choose as many as the note really benefits from (at most "
        f"{MAX_REFERENCES}); fewer good ones beat many weak ones. Give each a one-line `note` on what it is good "
        f"for. Only cite pages you actually retrieved. {UNTRUSTED_WEB}"
    )
    result = await run_structured(
        engine, role="reference_finder", job_id=job_id, prompt=prompt, model_cls=ReferenceList,
        tools=WEB_TOOLS, timeout_seconds=300,
    )
    kept = await keep_verified_sources(result.value.references, result.fetched_urls, check_live)
    ordered = sorted(kept, key=lambda r: KIND_RANK[r.kind])[:MAX_REFERENCES]
    logger.info("job %s: %r has %d verified reference(s) (agent proposed %d)", job_id[:8], node.title, len(ordered), len(result.value.references))
    return RunResult(value=ReferenceList(references=ordered), cost_usd=result.cost_usd, fetched_urls=result.fetched_urls)

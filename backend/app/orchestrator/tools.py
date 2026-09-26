"""Orchestrator tools: the cheap plan-forming signal (§5.1) and the
transactional boundary that replaces `git_guard`'s commit/revert now that
state is split across Postgres and Kùzu instead of one git repo (§8/§10.2
of docs/superpowers/specs/2026-09-24-multi-agent-architecture-design.md).

Plain, stateless functions taking explicit `AsyncSession`/`kuzu.Connection`
arguments — same repository-style pattern as `concept_repo.py`/
`graph_repo.py`, just spanning both stores since that's exactly what
`commit_job`/`rollback_job` need to do.
"""

import difflib
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

import kuzu
from sqlalchemy import delete, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Concept
from app.repositories.concept_repo import list_committed_concepts
from app.repositories.source_record_repo import read_source

if TYPE_CHECKING:
    from app.agents.text_agent import TextAgentOutput

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SourceSignals:
    content_length: int
    topic_hint: str | None
    max_title_similarity: float  # 0.0-1.0


async def get_source_signals(session: AsyncSession, source_id: str) -> SourceSignals:
    """Cheap, deterministic — no LLM call (spec §5.1). Reads the Source row
    and scores its content against every status='committed' concept title:
    `max_title_similarity` is the max over those titles of
    `difflib.SequenceMatcher(None, content[:500].lower(), title.lower()).ratio()`,
    or 0.0 when no committed concepts exist yet (not an error).
    """
    source = await read_source(session, source_id)
    committed = await list_committed_concepts(session)

    content_prefix = source.content[:500].lower()
    max_title_similarity = max(
        (
            difflib.SequenceMatcher(None, content_prefix, concept.title.lower()).ratio()
            for concept in committed
        ),
        default=0.0,
    )

    return SourceSignals(
        content_length=len(source.content),
        topic_hint=source.topic_hint,
        max_title_similarity=max_title_similarity,
    )


def should_run_graph_agent(text_output: "TextAgentOutput") -> bool:
    """Spec §5.1 step 3: plan revision once Text Agent's real output is
    available. Cheap, no extra LLM call — concepts_written already carries
    everything this decision needs: if nothing was created or updated this
    round, there's nothing for Graph Agent to relate; if anything was
    touched (created OR updated — an updated concept can still gain new
    relationships), Graph Agent gets a chance to reason about it."""
    return len(text_output.concepts_written) > 0


async def commit_job(session: AsyncSession, kuzu_conn: kuzu.Connection, job_id: str) -> None:
    """Flips every `job_id`-tagged pending record across both stores to
    committed (spec §10.2). `job_id` is kept on committed Concept rows for
    audit — nothing reads it as a "still pending" signal once status flips.

    The Kùzu half now runs against real pending edges written by the Graph
    Agent (Phase 5) as well as test-seeded ones — it was exercised here from
    day one so the two-store commit was correct before real relationships
    existed, not dead code.
    """
    try:
        concept_result = await session.execute(
            update(Concept)
            .where(Concept.job_id == job_id, Concept.status == "pending")
            .values(status="committed")
        )
        await session.commit()
        concept_count = concept_result.rowcount

        edge_result = kuzu_conn.execute(
            "MATCH (a:Concept)-[r:RELATES_TO]->(b:Concept) "
            "WHERE r.job_id = $job_id AND r.status = 'pending' "
            "SET r.status = 'committed' "
            "RETURN count(r)",
            {"job_id": job_id},
        )
        edge_count = edge_result.get_next()[0]
    except Exception:
        # No real cross-store transaction spans Postgres and Kùzu (accepted
        # limitation, spec §10.2) — a mid-function failure here can leave
        # the two stores inconsistent (e.g. concepts flipped to committed,
        # edges still pending). Log loudly so that's diagnosable, then
        # re-raise; the caller (job_service) owns marking the job failed.
        logger.exception("commit_job failed partway through — stores may be inconsistent: job_id=%s", job_id)
        raise

    logger.info(
        "job committed: job_id=%s concepts=%d edges=%d", job_id, concept_count, edge_count
    )


async def rollback_job(session: AsyncSession, kuzu_conn: kuzu.Connection, job_id: str) -> None:
    """Deletes every `job_id`-tagged pending record across both stores
    (spec §10.2) — mirrors commit_job's two-store scope."""
    try:
        concept_result = await session.execute(
            delete(Concept).where(Concept.job_id == job_id, Concept.status == "pending")
        )
        await session.commit()
        concept_count = concept_result.rowcount

        edge_result = kuzu_conn.execute(
            "MATCH (a:Concept)-[r:RELATES_TO]->(b:Concept) "
            "WHERE r.job_id = $job_id AND r.status = 'pending' "
            "DELETE r "
            "RETURN count(r)",
            {"job_id": job_id},
        )
        edge_count = edge_result.get_next()[0]
    except Exception:
        # Same no-real-cross-store-transaction caveat as commit_job — log
        # loudly, then re-raise; the caller owns marking the job failed.
        logger.exception("rollback_job failed partway through — stores may be inconsistent: job_id=%s", job_id)
        raise

    logger.info(
        "job rolled back: job_id=%s concepts=%d edges=%d", job_id, concept_count, edge_count
    )

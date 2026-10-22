"""Activities for the middle of the pipeline: research, writing, references, related links.

Each takes ids and loads what it needs from Postgres. Drafts are overwritten on re-run, so
Temporal can retry any of them safely.
"""

import asyncio
import logging

from temporalio import activity

from app.agents.runner import AgentOutputError
from app.engines.base import AgentEngine
from app.repositories import note_draft_repo
from app.services import draft_service
from app.workflows.activities.common import record_step
from app.workflows.activities.heartbeat import with_heartbeat
from app.workflows.models import PlanInfo

logger = logging.getLogger(__name__)


class WritingActivities:
    def __init__(self, session_factory, engine: AgentEngine, max_parallel: int) -> None:
        self._session_factory = session_factory
        self._engine = engine
        self._max_parallel = max_parallel

    async def _step(self, job_id: str, step: str, role: str, work) -> None:
        """Runs `work(session, ctx) -> cost`, records its cost, and records the cost of a failed attempt too."""
        try:
            async with self._session_factory() as session:
                ctx = await draft_service.load_context(session, job_id)
                cost = await with_heartbeat(work(session, ctx))
        except AgentOutputError as exc:
            await record_step(self._session_factory, job_id, step, role, exc.cost_usd, "failed", str(exc)[:500])
            raise
        await record_step(self._session_factory, job_id, step, role, cost)

    @activity.defn
    async def load_plan(self, job_id: str) -> PlanInfo:
        async with self._session_factory() as session:
            ctx = await draft_service.load_context(session, job_id)
        return draft_service.plan_info(ctx, self._max_parallel)

    @activity.defn
    async def research_leaf(self, job_id: str, node_key: str) -> None:
        await self._step(job_id, "research", "researcher", lambda s, c: draft_service.research_leaf(s, self._engine, c, node_key))

    @activity.defn
    async def write_core(self, job_id: str, node_key: str) -> None:
        await self._step(job_id, "write", "synthesizer", lambda s, c: draft_service.write_shared_core(s, self._engine, c, node_key))

    @activity.defn
    async def write_node(self, job_id: str, node_key: str, domain_slug: str, feedback: str | None = None) -> None:
        async with self._session_factory() as session:
            ctx = await draft_service.load_context(session, job_id)
        node = ctx.nodes[node_key]
        role = "synthesizer" if ctx.children.get(node_key) else "writer"
        await self._step(job_id, "write", role, lambda s, c: draft_service.write_draft(s, self._engine, c, node_key, domain_slug, feedback))

    @activity.defn
    async def find_node_references(self, job_id: str, node_key: str) -> None:
        await self._step(job_id, "references", "reference_finder", lambda s, c: draft_service.add_references(s, self._engine, c, node_key))

    @activity.defn
    async def link_related(self, job_id: str) -> None:
        async with self._session_factory() as session:
            draft_ids = [d.id for d in await note_draft_repo.list_for_job(session, job_id)]
        gate = asyncio.Semaphore(self._max_parallel)

        async def one(draft_id: str) -> float:
            async with gate, self._session_factory() as session:
                return await draft_service.add_related(session, self._engine, job_id, draft_id)

        async def all_drafts(session, ctx) -> float:
            return sum(await asyncio.gather(*(one(d) for d in draft_ids)))

        await self._step(job_id, "related", "linker", all_drafts)
        logger.info("job %s: related links added to %d draft(s)", job_id[:8], len(draft_ids))

    def activities(self) -> list:
        return [
            self.load_plan, self.research_leaf, self.write_core, self.write_node,
            self.find_node_references, self.link_related,
        ]

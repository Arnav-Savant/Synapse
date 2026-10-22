"""Activities for the first half of the pipeline: classify, outline, overlap.

Every activity takes ids and reads what it needs from Postgres, so nothing
large travels through Temporal's history.
"""

import asyncio
import logging

from temporalio import activity

from app.agents.classifier import classify
from app.agents.linker import judge_overlap
from app.agents.planner import plan_outline
from app.agents.runner import AgentOutputError
from app.agents.structurer import structure_content
from app.engines.base import AgentEngine
from app.repositories import agent_config_repo, domain_repo, job_repo, note_index_repo, outline_draft_repo
from app.schemas.domains import DomainSummary
from app.schemas.outline import Outline, validate_outline
from app.services.job_service import profiles_for_job
from app.workflows.activities.common import record_step
from app.workflows.activities.heartbeat import with_heartbeat

logger = logging.getLogger(__name__)

_DEFAULT_PLANNER_SEARCHES = 5


class OutlineActivities:
    def __init__(self, session_factory, engine: AgentEngine) -> None:
        self._session_factory = session_factory
        self._engine = engine

    async def _record(self, job_id: str, step: str, role: str, cost: float, status: str = "done", error: str | None = None) -> None:
        await record_step(self._session_factory, job_id, step, role, cost, status, error)

    @activity.defn
    async def classify_domains(self, job_id: str) -> list[str]:
        """The dropdown's choice, or the Classifier's pick for Auto-detect. Returns the resolved domain slugs."""
        async with self._session_factory() as session:
            job = await job_repo.get_job(session, job_id)
        snapshot = job.profile_snapshot or {}

        if job.domain_choice != "auto":
            if job.domain_choice not in snapshot:
                raise domain_repo.DomainNotFoundError(f"domain {job.domain_choice!r} was not in the job's snapshot")
            resolved, confidence = [job.domain_choice], None
        elif len(snapshot) == 1:
            resolved, confidence = list(snapshot), None
            logger.info("job %s: only one domain exists, skipping the classifier", job_id[:8])
        else:
            summaries = [DomainSummary(slug=slug, name=d["name"], purpose=d["purpose"]) for slug, d in snapshot.items()]
            result = await with_heartbeat(classify(self._engine, job_id=job_id, text=job.input_text, domains=summaries))
            await self._record(job_id, "classify", "classifier", result.cost_usd)
            resolved, confidence = result.value.domains, result.value.confidence

        async with self._session_factory() as session:
            await job_repo.set_resolved_domains(session, job_id, resolved, confidence)
        return resolved

    @activity.defn
    async def build_outline(self, job_id: str, feedback: str | None = None) -> None:
        """Planner (topic) or Structurer (content). On a re-plan the owner's edited tree, already stored as
        the draft, is passed back in with their feedback."""
        async with self._session_factory() as session:
            job = await job_repo.get_job(session, job_id)
            prior = await outline_draft_repo.get(session, job_id)
            planner_config = await agent_config_repo.get_agent_config(session, "planner")
        if not job.resolved_domains:
            raise ValueError("the job has no resolved domains yet")
        profiles = profiles_for_job(job, job.resolved_domains)

        role = "planner" if job.input_kind == "topic" else "structurer"
        try:
            await self._plan_or_structure(job, prior, planner_config, feedback, profiles, role)
        except AgentOutputError as exc:  # the failed attempts still cost money; keep that on the record
            await self._record(job_id, "outline", role, exc.cost_usd, status="failed", error=str(exc)[:500])
            raise

    async def _plan_or_structure(self, job, prior, planner_config, feedback, profiles, role: str) -> None:
        job_id = job.id
        if job.input_kind == "topic":
            max_searches = int(planner_config.params.get("max_searches", _DEFAULT_PLANNER_SEARCHES))
            result = await with_heartbeat(plan_outline(
                self._engine, job_id=job_id, topic=job.input_text, profiles=profiles,
                feedback=feedback, prior=prior, max_searches=max_searches,
            ))
        else:
            result = await with_heartbeat(structure_content(
                self._engine, job_id=job_id, content=job.input_text, profiles=profiles, feedback=feedback, prior=prior,
            ))

        outline = result.value.to_outline()
        previous_domains = {n.key: n.domains for n in prior.nodes} if prior else {}
        for node in outline.nodes:  # keep the owner's per-node domain choices for nodes that survived the re-plan
            node.domains = [d for d in previous_domains.get(node.key, []) if d in job.resolved_domains] or list(job.resolved_domains)
        async with self._session_factory() as session:
            await outline_draft_repo.save(session, job_id, outline, feedback)
        await self._record(job_id, "outline", role, result.cost_usd)

    @activity.defn
    async def store_outline(self, job_id: str, tree: Outline, feedback: str | None = None) -> list[str]:
        """Saves the owner's edited tree as the current draft. Returns what is wrong with it
        (nothing is saved then), so a bad edit keeps the job at the gate instead of failing it."""
        problems = validate_outline(tree)
        if problems:
            logger.warning("job %s: the edited outline was rejected: %s", job_id[:8], "; ".join(problems))
            return problems
        async with self._session_factory() as session:
            await outline_draft_repo.save(session, job_id, tree, feedback)
        logger.info("job %s: owner's outline stored (%d node(s))", job_id[:8], len(tree.nodes))
        return []

    @activity.defn
    async def compute_overlap(self, job_id: str) -> None:
        """One verdict per (node, domain): does it duplicate a note already in that vault?"""
        async with self._session_factory() as session:
            job = await job_repo.get_job(session, job_id)
            outline = await outline_draft_repo.get(session, job_id)
            domain_ids = {slug: (await domain_repo.get_by_slug(session, slug)).id for slug in job.resolved_domains}
        if outline is None:
            raise ValueError("there is no outline to check for overlap")

        async def judge(node, slug: str):
            async with self._session_factory() as session:
                candidates = await note_index_repo.find_candidates(
                    session, domain_ids[slug], title=node.title, aliases=[], summary=node.summary
                )
            return node, slug, await judge_overlap(self._engine, job_id=job_id, node=node, domain=slug, candidates=candidates)

        results = await with_heartbeat(asyncio.gather(*(judge(n, s) for n in outline.nodes for s in n.domains if s in domain_ids)))
        for node in outline.nodes:
            node.verdicts = {}
        by_key = {n.key: n for n in outline.nodes}
        total = 0.0
        for node, slug, result in results:
            by_key[node.key].verdicts[slug] = result.value
            total += result.cost_usd
        async with self._session_factory() as session:
            await outline_draft_repo.save(session, job_id, outline, None)
        await self._record(job_id, "overlap", "linker", total)
        merges = sum(1 for _, _, r in results if r.value.kind == "same")
        logger.info("job %s: overlap checked for %d (node, domain) pair(s); %d would merge into an existing note", job_id[:8], len(results), merges)

    def activities(self) -> list:
        return [self.classify_domains, self.build_outline, self.store_outline, self.compute_overlap]

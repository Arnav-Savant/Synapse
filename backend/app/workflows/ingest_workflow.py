"""One workflow per submission (spec §8). The body is deterministic: it never asks an
LLM what to do next, it routes on what activities and the owner return.

Part 1 (this file so far): classify -> outline -> overlap -> Gate 1.
A pipeline holds an admission slot only while it is executing; while it waits at a gate for the
owner it has handed the slot back, so waiting never blocks other jobs.
"""

import asyncio
from collections.abc import Callable
from datetime import timedelta
from typing import Any

from temporalio import workflow
from temporalio.exceptions import ActivityError, CancelledError

with workflow.unsafe.imports_passed_through():
    from app.schemas.validation import RoundSummary
    from app.services.commit_service import CommitSummary
    from app.workflows.models import (
        AGENT_HEARTBEAT_TIMEOUT,
        AGENT_RETRY,
        DB_RETRY,
        DraftDecision,
        MAX_QUALITY_ROUNDS,
        NodeFeedback,
        OutlineDecision,
        PlanInfo,
        WorkflowStatus,
        round_key,
        hold_slot,
        release_slot,
    )


class _JobCancelled(Exception):
    """The owner cancelled the job; unwinds the pipeline to its cleanup."""


def _readable(exc: BaseException) -> str:
    """The root cause's message, not Temporal's 'Activity task failed' wrapper."""
    while getattr(exc, "cause", None) is not None:
        exc = exc.cause
    return str(exc) or exc.__class__.__name__


@workflow.defn
class IngestTopicWorkflow:
    def __init__(self) -> None:
        self._step = "queued"
        self._awaiting_owner = False
        self._cancelled = False
        self._slot_granted = False
        self._outline_decision: OutlineDecision | None = None
        self._draft_decision: DraftDecision | None = None

    # -- signals and queries -------------------------------------------------

    @workflow.signal
    def outline_decision(self, decision: OutlineDecision) -> None:
        self._outline_decision = decision

    @workflow.signal
    def draft_decision(self, decision: DraftDecision) -> None:
        self._draft_decision = decision

    @workflow.signal
    def cancel(self) -> None:
        self._cancelled = True

    @workflow.signal
    def slot_granted(self) -> None:
        self._slot_granted = True

    @workflow.query
    def status(self) -> WorkflowStatus:
        return WorkflowStatus(step=self._step, awaiting_owner=self._awaiting_owner)

    # -- helpers ---------------------------------------------------------------

    async def _act(
        self, name: str, *args: Any, timeout: timedelta, agent: bool = False, result_type: type | None = None
    ) -> Any:
        """Runs an activity, but gives up at once if the owner cancels meanwhile."""
        task = asyncio.ensure_future(
            workflow.execute_activity(
                name,
                args=list(args),
                result_type=result_type,
                start_to_close_timeout=timeout,
                heartbeat_timeout=AGENT_HEARTBEAT_TIMEOUT if agent else None,
                retry_policy=AGENT_RETRY if agent else DB_RETRY,
            )
        )
        await workflow.wait_condition(lambda: task.done() or self._cancelled)
        if not task.done():
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, CancelledError, ActivityError):
                pass
            raise _JobCancelled()
        return task.result()

    async def _all(self, factories: list[Callable[[], Any]], limit: int) -> list[Any]:
        """Runs the activities in parallel, at most `limit` at once. If one fails or the owner cancels,
        the rest are cancelled too, so nothing keeps spending money for a job that has ended."""
        gate = asyncio.Semaphore(limit)

        async def run(factory: Callable[[], Any]) -> Any:
            async with gate:
                return await factory()

        tasks = [asyncio.ensure_future(run(f)) for f in factories]
        try:
            return list(await asyncio.gather(*tasks))
        except BaseException:
            for t in tasks:
                t.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            raise

    async def _wait_for(self, ready: Callable[[], bool]) -> None:
        await workflow.wait_condition(lambda: ready() or self._cancelled)
        if self._cancelled:
            raise _JobCancelled()

    async def _mark(self, job_id: str, step: str, status: str, awaiting_owner: bool = False, error: str = "") -> None:
        self._step, self._awaiting_owner = step, awaiting_owner
        await workflow.execute_activity(
            "mark_step", args=[job_id, step, status, awaiting_owner, error],
            start_to_close_timeout=timedelta(seconds=30), retry_policy=DB_RETRY,
        )

    async def _take_slot(self, job_id: str, step: str) -> None:
        self._slot_granted = False
        await self._mark(job_id, step, "queued")
        await hold_slot(workflow.info().workflow_id, lambda: self._slot_granted or self._cancelled)
        if self._cancelled:
            raise _JobCancelled()
        await self._mark(job_id, step, "running")

    # -- the pipeline -------------------------------------------------------------

    @workflow.run
    async def run(self, job_id: str) -> None:
        me = workflow.info().workflow_id
        try:
            await self._pipeline(job_id)
        except _JobCancelled:
            await release_slot(me)
            await self._end(job_id, "cancelled")
        except Exception as exc:  # a failed step ends this job, never the worker
            await release_slot(me)
            workflow.logger.error("job %s failed at step %s: %s", job_id[:8], self._step, _readable(exc))
            await self._end(job_id, "failed", f"{self._step} step failed: {_readable(exc)}")
        else:
            await release_slot(me)
            await self._end(job_id, "completed")

    async def _end(self, job_id: str, status: str, error: str | None = None) -> None:
        self._awaiting_owner = False
        await workflow.execute_activity(
            "end_job", args=[job_id, status, error], start_to_close_timeout=timedelta(seconds=60), retry_policy=DB_RETRY
        )

    async def _pipeline(self, job_id: str) -> None:
        me = workflow.info().workflow_id
        await self._take_slot(job_id, "classify")

        await self._act("classify_domains", job_id, timeout=timedelta(minutes=5), agent=True, result_type=list[str])
        self._step = "outline"
        await self._mark(job_id, "outline", "running")
        await self._act("build_outline", job_id, None, timeout=timedelta(minutes=20), agent=True)
        await self._mark(job_id, "place", "running")
        await self._act("place_topic", job_id, timeout=timedelta(minutes=10), agent=True)
        await self._mark(job_id, "overlap", "running")
        await self._act("compute_overlap", job_id, timeout=timedelta(minutes=10), agent=True)

        # Gate 1: outline approval. The slot goes back to the pool while the owner thinks.
        gate_error = ""  # why the last edit was rejected, shown to the owner at the gate
        while True:
            await release_slot(me)
            await self._mark(job_id, "outline_gate", "awaiting_owner", awaiting_owner=True, error=gate_error)
            gate_error = ""
            self._outline_decision = None
            await self._wait_for(lambda: self._outline_decision is not None)
            decision = self._outline_decision
            await self._take_slot(job_id, "outline")

            problems = await self._act(
                "store_outline", job_id, decision.tree, decision.feedback, timeout=timedelta(seconds=60), result_type=list[str]
            )
            if problems:  # a bad edit keeps the job at the gate, with the reason shown to the owner
                gate_error = "That outline was not accepted: " + "; ".join(problems)
                continue
            if decision.kind == "replan":
                await self._act("build_outline", job_id, decision.feedback, timeout=timedelta(minutes=20), agent=True)
                await self._mark(job_id, "place", "running")
                await self._act("place_topic", job_id, timeout=timedelta(minutes=10), agent=True)
                await self._mark(job_id, "overlap", "running")
                await self._act("compute_overlap", job_id, timeout=timedelta(minutes=10), agent=True)
                continue
            break

        await self._build_drafts(job_id)

    # -- part 2: research -> write -> references -> related -> validate -------------------------------

    async def _build_drafts(self, job_id: str) -> None:
        plan: PlanInfo = await self._act("load_plan", job_id, timeout=timedelta(seconds=60), result_type=PlanInfo)
        limit = plan.max_parallel
        leaves = [n for n in plan.nodes if n.is_leaf]

        if plan.topic_mode:  # content-given jobs skip research: the pasted material is the source
            await self._mark(job_id, "research", "running")
            await self._all(
                [lambda n=n: self._act("research_leaf", job_id, n.key, timeout=timedelta(minutes=20), agent=True) for n in leaves],
                limit,
            )

        await self._mark(job_id, "write", "running")
        shared = [n for n in leaves if len(n.domains) > 1]
        if shared:  # cross-domain notes share one domain-neutral core
            await self._all(
                [lambda n=n: self._act("write_core", job_id, n.key, timeout=timedelta(minutes=10), agent=True) for n in shared],
                limit,
            )
        # Children before parents, so each parent summarises what was actually written.
        for height in sorted({n.height for n in plan.nodes}):
            await self._all(
                [
                    lambda n=n, d=d: self._write_node(job_id, n.key, d, None)
                    for n in plan.nodes if n.height == height for d in n.domains
                ],
                limit,
            )

        await self._mark(job_id, "references", "running")
        await self._all(
            [lambda n=n: self._act("find_node_references", job_id, n.key, timeout=timedelta(minutes=10), agent=True) for n in leaves],
            limit,
        )
        await self._mark(job_id, "related", "running")
        await self._act("link_related", job_id, timeout=timedelta(minutes=20), agent=True)

        await self._validate_with_retries(job_id, limit)
        await self._draft_gate(job_id, limit)

    # -- Gate 2: draft review, feedback, commit ------------------------------------------------------

    async def _draft_gate(self, job_id: str, limit: int) -> None:
        me = workflow.info().workflow_id
        while True:
            await release_slot(me)
            await self._mark(job_id, "draft_gate", "awaiting_owner", awaiting_owner=True)
            self._draft_decision = None
            await self._wait_for(lambda: self._draft_decision is not None)
            decision = self._draft_decision
            await self._take_slot(job_id, "draft_gate")

            if decision.kind == "feedback":
                await self._apply_feedback(job_id, decision.feedback, limit)
                continue

            await self._mark(job_id, "commit", "running")
            summary: CommitSummary = await self._act(
                "commit_approved", job_id, decision.approve_node_keys, timeout=timedelta(minutes=10), result_type=CommitSummary
            )
            if summary.stale:
                # The file changed on disk after the draft was made. Nothing was overwritten; rebuild each
                # merge from the file as it is now and show the owner a fresh diff.
                await self._mark(job_id, "write", "running")
                await self._all([lambda k=k: self._write_node(job_id, k.split("|")[0], k.split("|")[1], None) for k in summary.stale], limit)
                await self._act("validate_drafts", job_id, summary.stale, {}, timeout=timedelta(minutes=30), agent=True, result_type=RoundSummary)
            if summary.stale or summary.failed:
                continue  # what is left goes back to the owner, flagged
            return

    async def _apply_feedback(self, job_id: str, items: list[NodeFeedback], limit: int) -> None:
        """Regenerates only what the owner pointed at, overwriting those drafts in place, then re-validates them."""
        plan: PlanInfo = await self._act("load_plan", job_id, timeout=timedelta(seconds=60), result_type=PlanInfo)
        known = {(n.key, d) for n in plan.nodes for d in n.domains}
        targets: dict[tuple[str, str], list[str]] = {}
        researched: set[str] = set()
        for fb in items:
            if fb.scope == "topic":  # the whole topic: every note, and every domain's twin of it
                pairs = sorted(known)
                text = fb.text
            else:
                pairs = [(fb.node_key, fb.domain_slug)]
                text = fb.text if fb.scope == "note" else (
                    f"Only change the section '{fb.section}'. {fb.text} Keep every other section exactly as it is."
                )
            for pair in pairs:
                if pair in known:
                    targets.setdefault(pair, []).append(text)
                else:
                    workflow.logger.warning("job %s: feedback for unknown draft %s ignored", job_id[:8], pair)
            if fb.re_research:
                researched |= {k for k, _ in pairs if k in {n.key for n in plan.nodes if n.is_leaf}}
        if not targets:
            return

        if plan.topic_mode and researched:
            await self._mark(job_id, "research", "running")
            await self._all(
                [lambda k=k: self._act("research_leaf", job_id, k, timeout=timedelta(minutes=20), agent=True) for k in sorted(researched)],
                limit,
            )
        await self._mark(job_id, "write", "running")
        height = {n.key: n.height for n in plan.nodes}
        for h in sorted({height[k] for k, _ in targets}):  # children before parents
            await self._all(
                [
                    lambda k=k, d=d, t=t: self._write_node(job_id, k, d, " ".join(t))
                    for (k, d), t in targets.items() if height[k] == h
                ],
                limit,
            )
        await self._mark(job_id, "validate", "running")
        await self._act(
            "validate_drafts", job_id, [round_key(k, d) for k, d in targets], {},
            timeout=timedelta(minutes=30), agent=True, result_type=RoundSummary,
        )

    def _write_node(self, job_id: str, node_key: str, domain: str, feedback: str | None) -> Any:
        return self._act("write_node", job_id, node_key, domain, feedback, timeout=timedelta(minutes=15), agent=True)

    async def _validate_with_retries(self, job_id: str, limit: int) -> RoundSummary:
        """Retry B: only the failing notes are rewritten, with their issues attached. At most
        MAX_QUALITY_ROUNDS rounds, stopping early when the same issues come back. Whatever still fails
        goes to Gate 2 with its flags; nothing is silently discarded."""
        await self._mark(job_id, "validate", "running")
        summary = await self._act(
            "validate_drafts", job_id, None, {}, timeout=timedelta(minutes=30), agent=True, result_type=RoundSummary
        )
        rounds = 0
        while summary.failing_keys and rounds < MAX_QUALITY_ROUNDS and not summary.no_progress:
            rounds += 1
            failing = summary
            workflow.logger.info("job %s: quality round %d, rewriting %d note(s)", job_id[:8], rounds, len(failing.failing_keys))
            await self._mark(job_id, "write", "running")
            await self._all(
                [
                    lambda k=k: self._write_node(job_id, k.split("|")[0], k.split("|")[1], failing.feedback.get(k))
                    for k in failing.failing_keys
                ],
                limit,
            )
            await self._mark(job_id, "validate", "running")
            summary = await self._act(
                "validate_drafts", job_id, failing.failing_keys, failing.codes,
                timeout=timedelta(minutes=30), agent=True, result_type=RoundSummary,
            )
        if summary.failing_keys:
            workflow.logger.warning("job %s: %d draft(s) still have issues; sending them to the owner flagged", job_id[:8], len(summary.failing_keys))
        return summary

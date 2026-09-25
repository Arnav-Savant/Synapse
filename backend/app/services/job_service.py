"""Orchestrates `jobs/` + `claude_runner/` into "process this source file".

This is where Phase 2's real logic lives — `api/jobs.py` just calls
`enqueue_processing` and returns; everything about running Claude Code,
committing or reverting the result, and recording job status happens here.
"""

import logging
from pathlib import Path

from app.claude_runner import git_guard, prompts, runner
from app.jobs import store
from app.jobs.queue import JobQueue
from app.jobs.store import Job
from app.services import graph_service

logger = logging.getLogger(__name__)


async def enqueue_processing(knowledge_repo_path: Path, source_relative_path: str, queue: JobQueue) -> Job:
    job = store.create_job(knowledge_repo_path, source_relative_path)
    await queue.enqueue(lambda: _process(knowledge_repo_path, job.id))
    return job


async def _process(knowledge_repo_path: Path, job_id: str) -> None:
    job = store.load_job(knowledge_repo_path, job_id)
    if job is None:
        logger.warning("job %s not found when worker picked it up", job_id)
        return

    job.status = "running"
    store.save_job(knowledge_repo_path, job)
    logger.info("job %s started: source=%s", job.id, job.source_relative_path)

    try:
        _run(knowledge_repo_path, job, await _invoke_claude(knowledge_repo_path, job))
    except git_guard.DirtyWorkingTreeError as exc:
        job.status = "failed"
        job.error = f"knowledge repo has uncommitted changes before this run: {exc}"
        logger.error("job %s failed: %s", job.id, job.error)
    except Exception as exc:  # noqa: BLE001 — job-failure boundary: record it, never raise out of here
        job.status = "failed"
        job.error = str(exc)
        logger.exception("job %s failed unexpectedly", job.id)

    store.save_job(knowledge_repo_path, job)
    if job.status == "succeeded":
        logger.info("job %s succeeded: cost_usd=%s committed=%s", job.id, job.cost_usd, job.committed_files)


async def _invoke_claude(knowledge_repo_path: Path, job: Job) -> runner.ClaudeRunResult | str:
    """Returns the run result, or an error string if the invocation itself failed."""
    git_guard.ensure_clean(knowledge_repo_path)
    try:
        prompt = prompts.ingestion_prompt(job.source_relative_path)
        return await runner.run_claude(knowledge_repo_path, prompt)
    except runner.ClaudeRunnerError as exc:
        return str(exc)


def _run(knowledge_repo_path: Path, job: Job, outcome: runner.ClaudeRunResult | str) -> None:
    commit_message = f"knowledge: process source/{job.source_relative_path} [job {job.id[:8]}]"
    committed = git_guard.finalize(knowledge_repo_path, commit_message)

    if isinstance(outcome, str):
        job.status = "failed"
        job.error = outcome
    elif outcome.is_error:
        job.status = "failed"
        job.error = outcome.result_text or "claude reported an error"
    else:
        job.status = "succeeded"
        job.result_summary = outcome.result_text
        job.committed_files = committed
        job.cost_usd = outcome.total_cost_usd
        if committed:
            graph_service.invalidate(knowledge_repo_path)

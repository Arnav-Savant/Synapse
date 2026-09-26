"""Orchestrates job lifecycle (`repositories/job_repo.py`) around the
LangGraph ingestion pipeline (`app/orchestrator/graph.py`).

This module owns `Job` status transitions end to end — `queued` ->
`running` -> a terminal status the compiled graph reports back
(`succeeded`/`failed`/`needs_review`). The pipeline logic itself (assess
signals, invoke the Text Agent, commit/rollback across Postgres+Kùzu) lives
in `orchestrator/`, not here; this module's only job is to never leave a
`Job` row stuck at `running`, even if the graph itself raises.
"""

import logging

from app.db.models import Job
from app.jobs.queue import JobQueue
from app.orchestrator.graph import build_graph
from app.orchestrator.state import OrchestratorState
from app.repositories import job_repo

logger = logging.getLogger(__name__)


async def enqueue_processing(session_factory, kuzu_conn, source_id: str, queue: JobQueue) -> Job:
    async with session_factory() as session:
        job = await job_repo.create_job(session, source_id=source_id)
    await queue.enqueue(lambda: _process(session_factory, kuzu_conn, job.id))
    return job


async def _process(session_factory, kuzu_conn, job_id: str) -> None:
    async with session_factory() as session:
        job = await job_repo.get_job(session, job_id)
        if job is None:
            logger.warning("job %s not found when worker picked it up", job_id)
            return

        job.status = "running"
        await job_repo.save_job(session, job)
        source_id = job.source_id

    logger.info("job %s started: source=%s", job_id, source_id)

    initial_state: OrchestratorState = {
        "job_id": job_id,
        "source_id": source_id,
        "signals": None,
        "text_agent_result": None,
        "should_run_graph_agent": False,
        "round_number": 0,
        "status": "running",
        "error": None,
    }

    final_status = "failed"
    try:
        compiled = build_graph(session_factory, kuzu_conn)
        final_state = await compiled.ainvoke(initial_state)
        final_status = final_state["status"]

        async with session_factory() as session:
            job = await job_repo.get_job(session, job_id)
            if job is None:
                logger.warning("job %s disappeared before its result could be recorded", job_id)
            else:
                job.status = final_state["status"]
                job.error = final_state.get("error")
                await job_repo.save_job(session, job)
    except Exception as exc:  # noqa: BLE001 — job-failure boundary: record it, never raise out of here
        logger.exception("job %s failed unexpectedly", job_id)
        final_status = "failed"
        async with session_factory() as session:
            job = await job_repo.get_job(session, job_id)
            if job is None:
                logger.warning("job %s disappeared before its failure could be recorded", job_id)
            else:
                job.status = "failed"
                job.error = str(exc)
                await job_repo.save_job(session, job)

    if final_status == "succeeded":
        logger.info("job %s succeeded", job_id)

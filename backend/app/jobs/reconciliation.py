"""Startup reconciliation for `Job` rows stuck at `status='running'`.

A `running` row means the backend crashed mid-job — the pipeline never got
to report a terminal status (`succeeded`/`failed`/`needs_review`) back to
`job_service`. This module cleans that up on the next startup rather than
leaving the job stuck forever, reusing `orchestrator.tools.rollback_job`
(already the correct two-store pending-record delete logic across Postgres
and Kùzu, per spec §10.2) rather than reimplementing it here.
"""

import logging

import kuzu

from app.orchestrator.tools import rollback_job
from app.repositories import job_repo

logger = logging.getLogger(__name__)


async def reconcile_orphaned_running_jobs(session_factory, kuzu_conn: kuzu.Connection) -> list[str]:
    """Call on backend startup. Returns the list of job_ids reconciled."""
    reconciled_ids: list[str] = []

    async with session_factory() as session:
        jobs = await job_repo.list_jobs(session)
        running_jobs = [job for job in jobs if job.status == "running"]

        for job in running_jobs:
            await rollback_job(session, kuzu_conn, job.id)
            job.status = "failed"
            job.error = "backend restarted while this job was running"
            await job_repo.save_job(session, job)
            reconciled_ids.append(job.id)
            logger.warning(
                "job %s reconciled to failed: backend restarted while it was running", job.id
            )

    return reconciled_ids

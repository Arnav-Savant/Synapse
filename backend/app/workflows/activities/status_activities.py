"""Activities that keep the `jobs` row (what the dashboard reads) in step with the workflow."""

import logging

from temporalio import activity

from app.repositories import job_repo

from app.services.job_service import finish_job_row

logger = logging.getLogger(__name__)


class StatusActivities:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    @activity.defn
    async def mark_step(
        self, job_id: str, step: str, status: str, awaiting_owner: bool = False, error: str | None = None
    ) -> None:
        async with self._session_factory() as session:
            await job_repo.set_status(session, job_id, status=status, current_step=step, awaiting_owner=awaiting_owner, error=error)
        logger.info("job %s: %s (%s)%s", job_id[:8], step, status, " waiting for the owner" if awaiting_owner else "")

    @activity.defn
    async def end_job(self, job_id: str, status: str, error: str | None = None) -> None:
        """Terminal transition for `completed`, `failed` and `cancelled`. Drafts are scratch space and go with the job."""
        async with self._session_factory() as session:
            dropped = await finish_job_row(session, job_id, status, error)
        if status == "failed":
            logger.error("job %s failed: %s", job_id[:8], error)
        else:
            logger.info("job %s %s; %d draft(s) discarded", job_id[:8], status, dropped)

    def activities(self) -> list:
        return [self.mark_step, self.end_job]

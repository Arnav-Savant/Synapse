"""The commit step: approved drafts become files. Deterministic, no agents."""

import logging

from temporalio import activity

from app.services import commit_service
from app.services.commit_service import CommitSummary

logger = logging.getLogger(__name__)


class CommitActivities:
    def __init__(self, session_factory) -> None:
        self._session_factory = session_factory

    @activity.defn
    async def commit_approved(self, job_id: str, node_keys: list[str] | None = None) -> CommitSummary:
        """Writes the approved drafts (None = all). Drafts that were not selected are discarded.
        Safe to run again after a crash."""
        async with self._session_factory() as session:
            summary = await commit_service.commit_drafts(session, job_id, node_keys)
            await commit_service.discard_unselected(session, job_id, node_keys)
        return summary

    def activities(self) -> list:
        return [self.commit_approved]

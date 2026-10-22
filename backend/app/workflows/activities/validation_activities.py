"""The validation step: deterministic rules, then the Validator agent, per draft."""

import asyncio
import logging

from temporalio import activity

from app.agents.runner import AgentOutputError
from app.engines.base import AgentEngine
from app.schemas.validation import RoundSummary
from app.services import draft_service
from app.workflows.activities.common import record_step
from app.workflows.activities.heartbeat import with_heartbeat

logger = logging.getLogger(__name__)


class ValidationActivities:
    def __init__(self, session_factory, engine: AgentEngine) -> None:
        self._session_factory = session_factory
        self._engine = engine

    @activity.defn
    async def validate_drafts(
        self, job_id: str, only_keys: list[str] | None = None, previous: dict[str, list[str]] | None = None
    ) -> RoundSummary:
        """`only_keys` are `node_key|domain` identifiers; None validates every draft."""
        try:
            async with self._session_factory() as session:
                ctx = await draft_service.load_context(session, job_id)
                summary, cost = await with_heartbeat(
                    draft_service.validate_drafts(session, self._engine, ctx, only_keys, previous or {})
                )
        except AgentOutputError as exc:
            await record_step(self._session_factory, job_id, "validate", "validator", exc.cost_usd, "failed", str(exc)[:500])
            raise
        await record_step(self._session_factory, job_id, "validate", "validator", cost)
        return summary

    def activities(self) -> list:
        return [self.validate_drafts]

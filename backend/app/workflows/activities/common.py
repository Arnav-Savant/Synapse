"""Bookkeeping shared by the agent-calling activities."""

from temporalio import activity

from app.repositories import job_repo, step_run_repo


async def record_step(
    session_factory, job_id: str, step: str, role: str | None, cost: float, status: str = "done", error: str | None = None
) -> None:
    """One audit row for the step and its cost added to the job total. Failed attempts are recorded too."""
    async with session_factory() as session:
        await step_run_repo.record(
            session, job_id=job_id, step=step, agent_role=role, attempt=activity.info().attempt,
            status=status, cost_usd=cost, error=error,
        )
        if cost:
            await job_repo.add_cost(session, job_id, cost)

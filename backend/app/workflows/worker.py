"""Temporal worker bootstrap. The worker runs inside the backend process, on the host,
so its activities can spawn `claude -p` with the host's login."""

import asyncio
import logging

from temporalio import workflow
from temporalio.client import Client
from temporalio.worker import Worker

from app.core.config import get_server_config
from app.engines.base import AgentEngine
from app.workflows.models import TASK_QUEUE

logger = logging.getLogger(__name__)

# Keep workflow log lines as plain sentences; the workflow/run ids are still attached as log record fields.
workflow.logger.workflow_info_on_message = False

_RESTART_DELAY_SECONDS = 5

# Filled in as workflows and activity groups are added (Tasks 17-20).
from app.workflows.admission_workflow import PipelineAdmissionWorkflow
from app.workflows.activities.commit_activities import CommitActivities
from app.workflows.activities.outline_activities import OutlineActivities
from app.workflows.activities.status_activities import StatusActivities
from app.workflows.activities.validation_activities import ValidationActivities
from app.workflows.activities.writing_activities import WritingActivities
from app.workflows.ingest_workflow import IngestTopicWorkflow

WORKFLOWS: list[type] = [PipelineAdmissionWorkflow, IngestTopicWorkflow]


def build_activities(session_factory, engine: AgentEngine) -> list:
    """Every activity, bound to the dependencies it needs."""
    max_parallel = get_server_config().max_claude_processes
    return [
        *StatusActivities(session_factory).activities(),
        *OutlineActivities(session_factory, engine).activities(),
        *WritingActivities(session_factory, engine, max_parallel).activities(),
        *ValidationActivities(session_factory, engine).activities(),
        *CommitActivities(session_factory).activities(),
    ]


async def _supervise(client: Client, session_factory, engine: AgentEngine) -> None:
    """Keeps a worker running. A crash is logged with its traceback and the worker restarts;
    only cancellation (backend shutdown) ends the loop."""
    config = get_server_config()
    while True:
        worker = Worker(
            client,
            task_queue=TASK_QUEUE,
            workflows=WORKFLOWS,
            activities=build_activities(session_factory, engine),
            # The engine's own semaphore is what caps concurrent `claude` processes; the activity
            # slots are looser so quick database activities never queue behind long agent calls.
            max_concurrent_activities=config.max_claude_processes * 4,
        )
        logger.info("temporal worker started on task queue %r", TASK_QUEUE)
        try:
            await worker.run()
            return
        except asyncio.CancelledError:
            logger.info("temporal worker shutting down")
            raise
        except Exception:
            logger.exception("temporal worker crashed; restarting in %ds", _RESTART_DELAY_SECONDS)
            await asyncio.sleep(_RESTART_DELAY_SECONDS)


def run_worker(client: Client, *, session_factory, engine: AgentEngine) -> asyncio.Task:
    return asyncio.create_task(_supervise(client, session_factory, engine), name="temporal-worker")

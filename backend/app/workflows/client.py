"""The Temporal client: one cached connection, with pydantic payload support."""

import asyncio
import logging

from temporalio.client import Client
from temporalio.contrib.pydantic import pydantic_data_converter

from app.core.config import ServerConfig

logger = logging.getLogger(__name__)

_CONNECT_ATTEMPTS = 6
_CONNECT_DELAY_SECONDS = 3

_client: Client | None = None


class TemporalUnavailableError(RuntimeError):
    """The Temporal server could not be reached."""


async def get_client(config: ServerConfig) -> Client:
    """Connects on first use and reuses the connection. Retries for a short while
    because the Temporal container may still be starting when the backend boots."""
    global _client
    if _client is not None:
        return _client
    last_error: Exception | None = None
    for attempt in range(1, _CONNECT_ATTEMPTS + 1):
        try:
            _client = await Client.connect(
                config.temporal_address, namespace=config.temporal_namespace, data_converter=pydantic_data_converter
            )
            logger.info("connected to Temporal at %s (namespace %s)", config.temporal_address, config.temporal_namespace)
            return _client
        except Exception as exc:  # the SDK raises RuntimeError for connection failures
            last_error = exc
            logger.warning("Temporal not reachable at %s (attempt %d/%d): %s", config.temporal_address, attempt, _CONNECT_ATTEMPTS, exc)
            if attempt < _CONNECT_ATTEMPTS:
                await asyncio.sleep(_CONNECT_DELAY_SECONDS)
    raise TemporalUnavailableError(
        f"cannot reach Temporal at {config.temporal_address}: {last_error}. Is it running? `docker compose up -d`"
    )


async def ensure_admission_started(client: Client) -> None:
    """Starts the single admission workflow if it is not already running. Safe to call any number of times."""
    from temporalio.common import WorkflowIDConflictPolicy

    from app.workflows.admission_workflow import PipelineAdmissionWorkflow
    from app.workflows.models import ADMISSION_WORKFLOW_ID, TASK_QUEUE

    await client.start_workflow(
        PipelineAdmissionWorkflow.run,
        id=ADMISSION_WORKFLOW_ID,
        task_queue=TASK_QUEUE,
        id_conflict_policy=WorkflowIDConflictPolicy.USE_EXISTING,
    )

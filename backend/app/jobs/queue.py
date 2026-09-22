"""Single-worker in-process job queue.

Every processing run targets the same knowledge repo, so runs are
serialized here rather than executed concurrently (docs/ARCHITECTURE.md
§5.5) — not because `claude -p` itself requires it, but because concurrent
writers to the same repo would race.

One `JobQueue` per app instance, created and started in `main.py`'s
lifespan and stored on `app.state` (not a module-level singleton — that
would tie the worker task to whatever event loop happened to be active on
first use, which breaks across independent app lifespans, e.g. one per
test).
"""

import asyncio
import logging
from collections.abc import Awaitable, Callable

from starlette.requests import Request

logger = logging.getLogger(__name__)

Task = Callable[[], Awaitable[None]]


class JobQueue:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[Task] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    def start(self) -> None:
        if self._worker_task is None:
            self._worker_task = asyncio.create_task(self._worker())

    async def stop(self) -> None:
        if self._worker_task is not None:
            self._worker_task.cancel()
            self._worker_task = None

    async def enqueue(self, task: Task) -> None:
        await self._queue.put(task)

    async def _worker(self) -> None:
        while True:
            task = await self._queue.get()
            try:
                await task()
            except Exception:  # noqa: BLE001 — one bad job must never kill the worker loop
                logger.exception("job queue task raised unexpectedly")
            finally:
                self._queue.task_done()


def get_job_queue(request: Request) -> JobQueue:
    return request.app.state.job_queue

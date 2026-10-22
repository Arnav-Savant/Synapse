"""Heartbeats for activities that wait on a `claude` subprocess, which is a black box."""

import asyncio
import contextlib
from collections.abc import Awaitable
from typing import TypeVar

from temporalio import activity

T = TypeVar("T")
_INTERVAL_SECONDS = 15


async def with_heartbeat(work: Awaitable[T]) -> T:
    """Awaits `work` while a background task heartbeats, so Temporal can tell a long agent call
    from a dead worker and can cancel the activity."""

    async def beat() -> None:
        while True:
            await asyncio.sleep(_INTERVAL_SECONDS)
            activity.heartbeat()

    task = asyncio.create_task(beat())
    try:
        return await work
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

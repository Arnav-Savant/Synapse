"""Per-domain vault lock: commits, deletes and reconcile of one vault never interleave."""

import asyncio
import logging
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

logger = logging.getLogger(__name__)

_locks: dict[str, asyncio.Lock] = {}


@asynccontextmanager
async def vault_lock(domain_slug: str) -> AsyncIterator[None]:
    lock = _locks.setdefault(domain_slug, asyncio.Lock())
    if lock.locked():
        logger.info("vault %r is busy, waiting for its lock", domain_slug)
    async with lock:
        yield

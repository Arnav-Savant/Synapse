"""Source record repository: the only module that reads the Postgres-backed
`sources` table (a DB row, distinct from the filesystem-backed `source/`
directory owned by `source_repo.py` — see docs/ARCHITECTURE.md §6 and the
multi-agent architecture spec, Phase 2 Task 2.5, for why these are separate,
unreconciled concepts for now).

Read-only: this is the only Source-record access surface exposed to the
Text Agent. Writing a `Source` row is deferred to a later phase (Phase 4) —
nothing calls it yet, and building it now would leave sources living in two
unreconciled places (this table and `source_repo.py`'s files).
"""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Source

logger = logging.getLogger(__name__)


class SourceRecordNotFoundError(LookupError):
    """No Source row exists for the given id."""


async def read_source(session: AsyncSession, source_id: str) -> Source:
    """Read-only. Raises SourceRecordNotFoundError if no matching row exists."""
    result = await session.execute(select(Source).where(Source.id == source_id))
    source = result.scalar_one_or_none()
    if source is None:
        logger.warning("source record not found: id=%s", source_id)
        raise SourceRecordNotFoundError(source_id)
    return source

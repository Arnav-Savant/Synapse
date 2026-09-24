import pytest
from sqlalchemy import text

from app.db.postgres import get_engine


@pytest.mark.asyncio
async def test_engine_connects():
    engine = get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1

import pytest
from sqlalchemy import text

from app.core.postgres_connection import postgres_connection


@pytest.mark.asyncio
async def test_engine_connects():
    engine = postgres_connection.get_engine()
    async with engine.connect() as conn:
        result = await conn.execute(text("SELECT 1"))
        assert result.scalar() == 1

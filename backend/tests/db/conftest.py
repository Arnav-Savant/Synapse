import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.postgres_connection import postgres_connection
from app.db.models import Base


@pytest.fixture
async def db_session():
    engine = postgres_connection.get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    session_factory = async_sessionmaker(bind=engine, expire_on_commit=False)
    async with session_factory() as session:
        yield session
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)
    # The engine is a module-level singleton (postgres_connection) shared
    # across the whole test session, but pytest-asyncio gives each test
    # function its own event loop by default; disposing the pool here
    # forces fresh connections to be opened against the next test's loop
    # instead of reusing ones bound to this test's now-closed loop.
    await engine.dispose()

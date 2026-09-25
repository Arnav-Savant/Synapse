import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.core.postgres_connection import postgres_connection
from app.db.models import Base, Source
from app.repositories.source_record_repo import SourceRecordNotFoundError, read_source


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
    await engine.dispose()


@pytest.mark.asyncio
async def test_read_source_returns_matching_row(db_session: AsyncSession):
    source = Source(content="raw study notes", topic_hint="prompt engineering")
    db_session.add(source)
    await db_session.commit()

    result = await read_source(db_session, source.id)

    assert result.id == source.id
    assert result.content == "raw study notes"
    assert result.topic_hint == "prompt engineering"
    assert result.uploaded_at is not None


@pytest.mark.asyncio
async def test_read_source_raises_when_missing(db_session: AsyncSession):
    with pytest.raises(SourceRecordNotFoundError):
        await read_source(db_session, "unknown-source-id")

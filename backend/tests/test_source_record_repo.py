import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Source
from app.repositories.source_record_repo import (
    SourceRecordNotFoundError,
    list_source_categories,
    read_source,
    write_source,
)


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


@pytest.mark.asyncio
async def test_write_source_happy_path(db_session: AsyncSession):
    created = await write_source(
        db_session,
        content="raw study notes",
        category="neural-networks",
        topic_hint="prompt engineering",
    )

    assert created.id is not None
    assert created.content == "raw study notes"
    assert created.category == "neural-networks"
    assert created.topic_hint == "prompt engineering"
    assert created.uploaded_at is not None

    fetched = await read_source(db_session, created.id)

    assert fetched.id == created.id
    assert fetched.content == "raw study notes"
    assert fetched.category == "neural-networks"
    assert fetched.topic_hint == "prompt engineering"
    assert fetched.uploaded_at is not None


@pytest.mark.asyncio
async def test_list_source_categories_returns_distinct_sorted_non_null(db_session: AsyncSession):
    db_session.add_all(
        [
            Source(content="a", category="neural-networks"),
            Source(content="b", category="prompt-engineering"),
            Source(content="c", category="neural-networks"),
            Source(content="d", category=None),
        ]
    )
    await db_session.commit()

    result = await list_source_categories(db_session)

    assert result == ["neural-networks", "prompt-engineering"]


@pytest.mark.asyncio
async def test_list_source_categories_empty_table_returns_empty_list(db_session: AsyncSession):
    result = await list_source_categories(db_session)

    assert result == []

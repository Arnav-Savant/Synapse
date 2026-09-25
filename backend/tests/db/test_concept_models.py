import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Concept, Job, Source


@pytest.mark.asyncio
async def test_source_is_immutable_by_convention(db_session: AsyncSession):
    src = Source(content="raw study notes", topic_hint=None)
    db_session.add(src)
    await db_session.commit()
    assert src.id is not None
    assert src.uploaded_at is not None


@pytest.mark.asyncio
async def test_concept_staging_fields(db_session: AsyncSession):
    job = Job(id="job-1", source_id="src-1", status="running")
    db_session.add(job)
    await db_session.flush()

    concept = Concept(
        title="Backpropagation",
        category="neural-networks",
        body="Backprop computes gradients via the chain rule.",
        metadata_={"aliases": ["backprop"]},
        status="pending",
        job_id="job-1",
    )
    db_session.add(concept)
    await db_session.commit()
    assert concept.status == "pending"
    assert concept.metadata_["aliases"] == ["backprop"]

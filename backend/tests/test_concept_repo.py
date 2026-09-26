import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Concept, Job
from app.repositories.concept_repo import (
    ConceptMetadata,
    ConceptNotFoundError,
    create_concept,
    get_concept,
    get_concept_metadata,
    list_committed_concepts,
    search_concepts,
    update_concept,
    update_concept_content,
)


async def _make_job(session: AsyncSession, job_id: str) -> Job:
    job = Job(id=job_id, source_id="src-1", status="running")
    session.add(job)
    await session.flush()
    return job


@pytest.mark.asyncio
async def test_get_concept_happy_path(db_session: AsyncSession):
    concept = Concept(
        title="Backpropagation",
        category="neural-networks",
        body="Backprop computes gradients via the chain rule.",
        metadata_={"aliases": ["backprop"]},
        status="committed",
    )
    db_session.add(concept)
    await db_session.flush()

    fetched = await get_concept(db_session, concept.id)

    assert fetched.id == concept.id
    assert fetched.title == "Backpropagation"
    assert fetched.body == "Backprop computes gradients via the chain rule."


@pytest.mark.asyncio
async def test_get_concept_not_found_raises(db_session: AsyncSession):
    with pytest.raises(ConceptNotFoundError):
        await get_concept(db_session, "does-not-exist")


@pytest.mark.asyncio
async def test_get_concept_metadata_excludes_body(db_session: AsyncSession):
    concept = Concept(
        title="Gradient Descent",
        category="optimization",
        body="Iteratively updates parameters to minimize a loss function.",
        metadata_={"aliases": []},
        status="committed",
    )
    db_session.add(concept)
    await db_session.flush()

    result = await get_concept_metadata(db_session, concept.id)

    assert result.id == concept.id
    assert result.title == "Gradient Descent"
    assert result.category == "optimization"
    assert not hasattr(result, "body")
    assert ConceptMetadata.__dataclass_fields__.keys() == {"id", "title", "category"}


@pytest.mark.asyncio
async def test_get_concept_metadata_not_found_raises(db_session: AsyncSession):
    with pytest.raises(ConceptNotFoundError):
        await get_concept_metadata(db_session, "does-not-exist")


@pytest.mark.asyncio
async def test_search_concepts_matches_title_substring(db_session: AsyncSession):
    db_session.add(
        Concept(title="Prompt Injection", category="llm-security", body="...", metadata_={}, status="committed")
    )
    db_session.add(
        Concept(title="Few-Shot Prompting", category="prompt-engineering", body="...", metadata_={}, status="committed")
    )
    await db_session.flush()

    results = await search_concepts(db_session, "injection")

    assert [r.title for r in results] == ["Prompt Injection"]


@pytest.mark.asyncio
async def test_search_concepts_matches_alias_substring(db_session: AsyncSession):
    db_session.add(
        Concept(
            title="Backpropagation",
            category="neural-networks",
            body="...",
            metadata_={"aliases": ["backprop"]},
            status="committed",
        )
    )
    await db_session.flush()

    results = await search_concepts(db_session, "backprop")

    assert [r.title for r in results] == ["Backpropagation"]


@pytest.mark.asyncio
async def test_search_concepts_includes_own_job_pending_concepts(db_session: AsyncSession):
    await _make_job(db_session, "job-a")
    db_session.add(
        Concept(
            title="Jailbreaking",
            category="llm-security",
            body="...",
            metadata_={},
            status="pending",
            job_id="job-a",
        )
    )
    await db_session.flush()

    results = await search_concepts(db_session, "jailbreak", job_id="job-a")

    assert [r.title for r in results] == ["Jailbreaking"]


@pytest.mark.asyncio
async def test_search_concepts_excludes_other_job_pending_concepts(db_session: AsyncSession):
    await _make_job(db_session, "job-a")
    await _make_job(db_session, "job-b")
    db_session.add(
        Concept(
            title="Jailbreaking",
            category="llm-security",
            body="...",
            metadata_={},
            status="pending",
            job_id="job-a",
        )
    )
    await db_session.flush()

    results = await search_concepts(db_session, "jailbreak", job_id="job-b")

    assert results == []

    results_no_job = await search_concepts(db_session, "jailbreak")

    assert results_no_job == []


@pytest.mark.asyncio
async def test_create_concept_defaults_to_pending_with_job_id(db_session: AsyncSession):
    await _make_job(db_session, "job-a")

    concept = await create_concept(
        db_session,
        title="Attention Mechanism",
        category="transformers",
        body="Weighs input tokens by relevance.",
        metadata={"aliases": ["self-attention"]},
        job_id="job-a",
    )

    assert concept.id is not None
    assert concept.status == "pending"
    assert concept.job_id == "job-a"
    assert concept.title == "Attention Mechanism"


@pytest.mark.asyncio
async def test_update_concept_partial_update_preserves_untouched_fields(db_session: AsyncSession):
    await _make_job(db_session, "job-a")
    concept = Concept(
        title="Transformer",
        category="architectures",
        body="Original body.",
        metadata_={"aliases": ["transformers"]},
        status="committed",
    )
    db_session.add(concept)
    await db_session.flush()

    updated = await update_concept(db_session, concept_id=concept.id, job_id="job-a", body="Updated body.")

    assert updated.body == "Updated body."
    assert updated.metadata_ == {"aliases": ["transformers"]}


@pytest.mark.asyncio
async def test_update_concept_restages_committed_concept_to_pending(db_session: AsyncSession):
    await _make_job(db_session, "job-old")
    await _make_job(db_session, "job-new")
    concept = Concept(
        title="Overfitting",
        category="machine-learning",
        body="...",
        metadata_={},
        status="committed",
        job_id="job-old",
    )
    db_session.add(concept)
    await db_session.flush()

    updated = await update_concept(db_session, concept_id=concept.id, job_id="job-new", metadata={"aliases": ["overfit"]})

    assert updated.status == "pending"
    assert updated.job_id == "job-new"
    assert updated.metadata_ == {"aliases": ["overfit"]}


@pytest.mark.asyncio
async def test_update_concept_not_found_raises(db_session: AsyncSession):
    with pytest.raises(ConceptNotFoundError):
        await update_concept(db_session, concept_id="does-not-exist", job_id="job-a", body="x")


@pytest.mark.asyncio
async def test_list_committed_concepts_excludes_pending(db_session: AsyncSession):
    await _make_job(db_session, "job-a")
    db_session.add(
        Concept(title="Backpropagation", category="neural-networks", body="...", metadata_={}, status="committed")
    )
    db_session.add(
        Concept(title="Attention Mechanism", category="transformers", body="...", metadata_={}, status="committed")
    )
    db_session.add(
        Concept(
            title="Jailbreaking",
            category="llm-security",
            body="...",
            metadata_={},
            status="pending",
            job_id="job-a",
        )
    )
    await db_session.flush()

    results = await list_committed_concepts(db_session)

    assert [r.title for r in results] == ["Attention Mechanism", "Backpropagation"]
    assert all(isinstance(r, ConceptMetadata) for r in results)


@pytest.mark.asyncio
async def test_list_committed_concepts_empty_when_none_committed(db_session: AsyncSession):
    await _make_job(db_session, "job-a")
    db_session.add(
        Concept(
            title="Jailbreaking",
            category="llm-security",
            body="...",
            metadata_={},
            status="pending",
            job_id="job-a",
        )
    )
    await db_session.flush()

    results = await list_committed_concepts(db_session)

    assert results == []


@pytest.mark.asyncio
async def test_update_concept_content_sets_committed_and_leaves_job_id_untouched(db_session: AsyncSession):
    await _make_job(db_session, "job-a")
    concept = Concept(
        title="Overfitting",
        category="machine-learning",
        body="Original body.",
        metadata_={"aliases": []},
        status="pending",
        job_id="job-a",
    )
    db_session.add(concept)
    await db_session.flush()

    updated = await update_concept_content(
        db_session, concept_id=concept.id, body="Edited body.", metadata={"aliases": ["overfit"]}
    )

    assert updated.status == "committed"
    assert updated.body == "Edited body."
    assert updated.metadata_ == {"aliases": ["overfit"]}
    assert updated.job_id == "job-a"


@pytest.mark.asyncio
async def test_update_concept_content_not_found_raises(db_session: AsyncSession):
    with pytest.raises(ConceptNotFoundError):
        await update_concept_content(db_session, concept_id="does-not-exist", body="x", metadata={})

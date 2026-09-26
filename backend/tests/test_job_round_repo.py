import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Job
from app.repositories.job_round_repo import create_job_round, list_job_rounds


async def _make_job(session: AsyncSession, job_id: str) -> Job:
    job = Job(id=job_id, source_id="src-1", status="running")
    session.add(job)
    await session.flush()
    return job


@pytest.mark.asyncio
async def test_create_job_round_happy_path(db_session: AsyncSession):
    await _make_job(db_session, "job-a")
    structured_output = {
        "segmentation": [{"title": "A"}, {"title": "B"}],
        "notes": "some notes",
    }

    round_ = await create_job_round(
        db_session,
        job_id="job-a",
        round_number=1,
        agent_type="text",
        prompt_delta="delta text",
        output_summary="created 2 concepts",
        structured_output_json=structured_output,
        cost_usd=0.01,
    )

    assert round_.id is not None
    assert round_.job_id == "job-a"
    assert round_.round_number == 1
    assert round_.agent_type == "text"
    assert round_.prompt_delta == "delta text"
    assert round_.output_summary == "created 2 concepts"
    assert round_.structured_output_json == structured_output
    assert round_.cost_usd == pytest.approx(0.01)


@pytest.mark.asyncio
async def test_list_job_rounds_ordered_by_round_number(db_session: AsyncSession):
    await _make_job(db_session, "job-a")

    await create_job_round(
        db_session,
        job_id="job-a",
        round_number=2,
        agent_type="graph",
        prompt_delta=None,
        output_summary="round 2",
        structured_output_json=None,
        cost_usd=None,
    )
    await create_job_round(
        db_session,
        job_id="job-a",
        round_number=1,
        agent_type="text",
        prompt_delta=None,
        output_summary="round 1",
        structured_output_json=None,
        cost_usd=None,
    )

    rounds = await list_job_rounds(db_session, "job-a")

    assert [r.round_number for r in rounds] == [1, 2]


@pytest.mark.asyncio
async def test_list_job_rounds_empty_for_job_with_no_rounds(db_session: AsyncSession):
    await _make_job(db_session, "job-a")

    rounds = await list_job_rounds(db_session, "job-a")

    assert rounds == []

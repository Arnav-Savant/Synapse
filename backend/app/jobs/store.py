"""Job records: one JSON file per processing run under `.synapse/jobs/`.

No database (docs/ARCHITECTURE.md §7) — this is the only module that reads
or writes that directory.
"""

import json
import logging
import uuid
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal

logger = logging.getLogger(__name__)

JobStatus = Literal["queued", "running", "succeeded", "failed"]


@dataclass
class Job:
    id: str
    source_relative_path: str
    status: JobStatus
    created_at: str
    updated_at: str
    result_summary: str | None = None
    error: str | None = None
    committed_files: list[str] = field(default_factory=list)
    cost_usd: float | None = None


def _jobs_dir(knowledge_repo_path: Path) -> Path:
    return knowledge_repo_path / ".synapse" / "jobs"


def _job_path(knowledge_repo_path: Path, job_id: str) -> Path:
    return _jobs_dir(knowledge_repo_path) / f"{job_id}.json"


def _now() -> str:
    return datetime.now(UTC).isoformat()


def create_job(knowledge_repo_path: Path, source_relative_path: str) -> Job:
    now = _now()
    job = Job(
        id=uuid.uuid4().hex,
        source_relative_path=source_relative_path,
        status="queued",
        created_at=now,
        updated_at=now,
    )
    save_job(knowledge_repo_path, job)
    logger.info("job created: id=%s source=%s", job.id, source_relative_path)
    return job


def save_job(knowledge_repo_path: Path, job: Job) -> None:
    job.updated_at = _now()
    jobs_dir = _jobs_dir(knowledge_repo_path)
    jobs_dir.mkdir(parents=True, exist_ok=True)
    _job_path(knowledge_repo_path, job.id).write_text(json.dumps(asdict(job), indent=2), encoding="utf-8")


def load_job(knowledge_repo_path: Path, job_id: str) -> Job | None:
    path = _job_path(knowledge_repo_path, job_id)
    if not path.is_file():
        return None
    return Job(**json.loads(path.read_text(encoding="utf-8")))


def list_jobs(knowledge_repo_path: Path) -> list[Job]:
    jobs_dir = _jobs_dir(knowledge_repo_path)
    if not jobs_dir.is_dir():
        return []
    jobs = [Job(**json.loads(path.read_text(encoding="utf-8"))) for path in jobs_dir.glob("*.json")]
    return sorted(jobs, key=lambda j: j.created_at, reverse=True)


def reconcile_orphaned_running_jobs(knowledge_repo_path: Path) -> list[Job]:
    """Call on backend startup. A job stuck in "running" means the backend
    died mid-run — mark it failed rather than leaving it stuck forever."""
    reconciled = []
    for job in list_jobs(knowledge_repo_path):
        if job.status == "running":
            job.status = "failed"
            job.error = "backend restarted while this job was running"
            save_job(knowledge_repo_path, job)
            reconciled.append(job)
            logger.warning("job %s reconciled to failed: backend restarted while it was running", job.id)
    return reconciled

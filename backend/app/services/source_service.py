"""Orchestrates `repositories/source_repo.py` for the sources API.

The real logic here: auto-filing (category/filename) via real Claude
reasoning when the caller doesn't supply them, collision-safe naming for
auto-filed sources, committing each new/updated source file immediately
(`claude_runner/git_guard.py`) so the knowledge repo's tree is already
clean by the time a processing job's `ensure_clean` check runs, and
auto-enqueuing that processing job right after — pasting content and
having the knowledge base update is meant to be one action, not two — see
docs/ARCHITECTURE.md §14.2: routes stay thin, services hold the logic.
"""

from pathlib import Path

from app.claude_runner import git_guard, naming
from app.jobs.queue import JobQueue
from app.jobs.store import Job
from app.repositories import source_repo
from app.repositories.source_repo import SourceFile
from app.services import job_service

_TEXT_EXTENSIONS = (".md", ".txt")


def list_sources(knowledge_repo_path: Path) -> list[SourceFile]:
    return source_repo.list_sources(knowledge_repo_path)


def read_source(knowledge_repo_path: Path, relative_path: str) -> str:
    return source_repo.read_source(knowledge_repo_path, relative_path)


async def create_text_source(
    knowledge_repo_path: Path,
    content: str,
    queue: JobQueue,
    category: str | None = None,
    filename: str | None = None,
    topic_hint: str | None = None,
) -> tuple[SourceFile, Job]:
    """`category`/`filename` are optional — when either is missing, Claude
    Code decides them by looking at what already exists under `source/`
    (see `CLAUDE.md`-style reasoning in `claude_runner/naming.py`, not a
    slugify heuristic). An explicitly-given filename can intentionally
    overwrite an existing file (the caller knows what they're targeting);
    an auto-suggested one never silently collides with existing material —
    it gets a numeric suffix instead.

    Returns the written source together with the processing job enqueued
    for it — saving and processing are one action from the caller's side.
    """
    auto_named = not category or not filename

    if auto_named:
        suggested_category, suggested_filename = await naming.suggest_source_location(
            knowledge_repo_path, content, topic_hint
        )
        category = category or suggested_category
        filename = filename or suggested_filename

    if not filename.endswith(_TEXT_EXTENSIONS):
        filename = f"{filename}.md"

    if auto_named:
        filename = _unique_filename(knowledge_repo_path, category, filename)

    source = source_repo.write_text_source(knowledge_repo_path, category, filename, content)
    _commit_source(knowledge_repo_path, source)
    job = await job_service.enqueue_processing(knowledge_repo_path, source.relative_path, queue)
    return source, job


def upload_binary_source(knowledge_repo_path: Path, filename: str, data: bytes) -> SourceFile:
    source = source_repo.write_binary_source(knowledge_repo_path, filename, data)
    _commit_source(knowledge_repo_path, source)
    return source


def _unique_filename(knowledge_repo_path: Path, category: str, filename: str) -> str:
    stem, _, ext = filename.rpartition(".")
    root = knowledge_repo_path / "source" / category
    candidate = filename
    counter = 2
    while (root / candidate).exists():
        candidate = f"{stem}-{counter}.{ext}"
        counter += 1
    return candidate


def _commit_source(knowledge_repo_path: Path, source: SourceFile) -> None:
    relative_path = f"source/{source.relative_path}"
    git_guard.commit_path(knowledge_repo_path, relative_path, f"source: add {source.relative_path}")

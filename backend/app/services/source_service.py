"""Orchestrates `repositories/source_repo.py` for the sources API.

The real logic here: filename normalization, and committing each new/updated
source file immediately (`claude_runner/git_guard.py`) so the knowledge
repo's tree is already clean by the time a processing job's `ensure_clean`
check runs — see docs/ARCHITECTURE.md §14.2: routes stay thin, services
hold the logic.
"""

from pathlib import Path

from app.claude_runner import git_guard
from app.repositories import source_repo
from app.repositories.source_repo import SourceFile

_TEXT_EXTENSIONS = (".md", ".txt")


def list_sources(knowledge_repo_path: Path) -> list[SourceFile]:
    return source_repo.list_sources(knowledge_repo_path)


def read_source(knowledge_repo_path: Path, relative_path: str) -> str:
    return source_repo.read_source(knowledge_repo_path, relative_path)


def create_text_source(knowledge_repo_path: Path, category: str, filename: str, content: str) -> SourceFile:
    if not filename.endswith(_TEXT_EXTENSIONS):
        filename = f"{filename}.md"
    source = source_repo.write_text_source(knowledge_repo_path, category, filename, content)
    _commit_source(knowledge_repo_path, source)
    return source


def upload_binary_source(knowledge_repo_path: Path, filename: str, data: bytes) -> SourceFile:
    source = source_repo.write_binary_source(knowledge_repo_path, filename, data)
    _commit_source(knowledge_repo_path, source)
    return source


def _commit_source(knowledge_repo_path: Path, source: SourceFile) -> None:
    relative_path = f"source/{source.relative_path}"
    git_guard.commit_path(knowledge_repo_path, relative_path, f"source: add {source.relative_path}")

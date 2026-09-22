"""Orchestrates `repositories/knowledge_repo.py` for the knowledge API.

Phase 1: read-only listing/reading of raw file content. The write path and
frontmatter-aware operations (parsing, merging, graph cache invalidation)
land in Phase 3/5 — this module grows into them, it isn't pre-built now.
"""

from pathlib import Path

from app.repositories import knowledge_repo


def list_knowledge(knowledge_repo_path: Path) -> list[str]:
    return knowledge_repo.list_knowledge_slugs(knowledge_repo_path)


def read_knowledge(knowledge_repo_path: Path, slug: str) -> str:
    return knowledge_repo.read_knowledge(knowledge_repo_path, slug)

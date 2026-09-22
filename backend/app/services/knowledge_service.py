"""Orchestrates `repositories/knowledge_repo.py` for the knowledge API.

Read path: list slugs, read+parse a concept. Write path (Phase 5):
validate the incoming text via `knowledge/frontmatter.py`, refuse a
slug/id mismatch, auto-refresh `updated`, write back, commit immediately
(`claude_runner/git_guard.py` — same reasoning as source writes: an
uncommitted manual edit would fail the next processing job's clean-tree
check), and invalidate the graph cache.
"""

from dataclasses import replace
from datetime import date
from pathlib import Path

from app.claude_runner import git_guard
from app.knowledge import frontmatter
from app.knowledge.frontmatter import FrontmatterError, ParsedConcept
from app.repositories import knowledge_repo
from app.services import graph_service


def list_knowledge(knowledge_repo_path: Path) -> list[str]:
    return knowledge_repo.list_knowledge_slugs(knowledge_repo_path)


def read_knowledge(knowledge_repo_path: Path, slug: str) -> tuple[ParsedConcept, str]:
    raw = knowledge_repo.read_knowledge(knowledge_repo_path, slug)
    return frontmatter.parse(raw), raw


def update_knowledge(knowledge_repo_path: Path, slug: str, raw_content: str) -> str:
    parsed = frontmatter.parse(raw_content)
    if parsed.id != slug:
        raise FrontmatterError(f"frontmatter id '{parsed.id}' does not match concept '{slug}'")

    refreshed = replace(parsed, updated=date.today().isoformat())
    serialized = frontmatter.serialize(refreshed)

    knowledge_repo.write_knowledge(knowledge_repo_path, slug, serialized)
    git_guard.commit_path(knowledge_repo_path, f"knowledge/{slug}.md", f"knowledge: manual edit of {slug}")
    graph_service.invalidate(knowledge_repo_path)

    return serialized

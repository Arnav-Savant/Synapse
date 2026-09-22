"""Knowledge file repository: the only module that reads/writes `knowledge/`.

Phase 1 only needs list/read of raw file content. Frontmatter-aware parsing
is introduced in Phase 3 (`app/knowledge/frontmatter.py`) and layered on top
of what this module returns, not duplicated here. The write path (Phase 5)
is added to this module when it's needed, not before.
"""

from pathlib import Path

from app.repositories.paths import resolve_within


class KnowledgeFileNotFoundError(FileNotFoundError):
    """No knowledge file exists for the given slug."""


def _knowledge_root(knowledge_repo_path: Path) -> Path:
    return knowledge_repo_path / "knowledge"


def list_knowledge_slugs(knowledge_repo_path: Path) -> list[str]:
    root = _knowledge_root(knowledge_repo_path)
    if not root.is_dir():
        return []

    return sorted(path.stem for path in root.glob("*.md") if path.is_file())


def read_knowledge(knowledge_repo_path: Path, slug: str) -> str:
    root = _knowledge_root(knowledge_repo_path)
    target = resolve_within(root, f"{slug}.md")
    if not target.is_file():
        raise KnowledgeFileNotFoundError(slug)
    return target.read_text(encoding="utf-8")

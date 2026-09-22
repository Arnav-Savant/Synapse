"""Knowledge file repository: the only module that reads/writes `knowledge/`.

Raw list/read/write of file content. Frontmatter-aware parsing is
`app/knowledge/frontmatter.py`, layered on top of what this module returns,
not duplicated here.
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


def write_knowledge(knowledge_repo_path: Path, slug: str, content: str) -> None:
    root = _knowledge_root(knowledge_repo_path)
    target = resolve_within(root, f"{slug}.md")
    if not target.is_file():
        raise KnowledgeFileNotFoundError(slug)
    target.write_text(content, encoding="utf-8")

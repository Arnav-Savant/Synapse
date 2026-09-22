"""Source file repository: the only module that reads/writes `source/`.

Raw material is created here and never modified by anything else in the
backend — `source/` is append-only from the app's perspective (see
docs/ARCHITECTURE.md §4.3; the processing engine's own restriction on
`source/` is separate and enforced in Phase 2).
"""

from dataclasses import dataclass
from pathlib import Path

from app.repositories.paths import resolve_within

UPLOADS_CATEGORY = "_uploads"


@dataclass(frozen=True)
class SourceFile:
    category: str
    filename: str
    relative_path: str
    size_bytes: int


def _source_root(knowledge_repo_path: Path) -> Path:
    return knowledge_repo_path / "source"


def _to_source_file(root: Path, target: Path) -> SourceFile:
    relative = target.relative_to(root)
    category = relative.parent.as_posix() if relative.parent != Path(".") else ""
    return SourceFile(
        category=category,
        filename=target.name,
        relative_path=relative.as_posix(),
        size_bytes=target.stat().st_size,
    )


def list_sources(knowledge_repo_path: Path) -> list[SourceFile]:
    root = _source_root(knowledge_repo_path)
    if not root.is_dir():
        return []

    return [
        _to_source_file(root, path)
        for path in sorted(root.rglob("*"))
        if path.is_file() and path.name != ".gitkeep"
    ]


def write_text_source(knowledge_repo_path: Path, category: str, filename: str, content: str) -> SourceFile:
    root = _source_root(knowledge_repo_path)
    target = resolve_within(root, category, filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")
    return _to_source_file(root, target)


def write_binary_source(knowledge_repo_path: Path, filename: str, data: bytes) -> SourceFile:
    root = _source_root(knowledge_repo_path)
    target = resolve_within(root, UPLOADS_CATEGORY, filename)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(data)
    return _to_source_file(root, target)

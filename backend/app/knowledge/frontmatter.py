"""Frontmatter parsing: split a knowledge file's YAML frontmatter from its
body and turn it into structured data. Pure function — no I/O, no
framework dependency (docs/ARCHITECTURE.md §14.2).

Only `parse()` exists for now. A `serialize()`/write path is added in
Phase 5 when the knowledge editor actually needs to write files back —
not built speculatively ahead of that (§14.3).
"""

from dataclasses import dataclass, field

import yaml

_DELIMITER = "---"


class FrontmatterError(ValueError):
    """A knowledge file's frontmatter is missing or malformed."""


@dataclass(frozen=True)
class Relationship:
    type: str
    target: str
    note: str | None = None


@dataclass(frozen=True)
class ParsedConcept:
    id: str
    title: str
    aliases: list[str] = field(default_factory=list)
    domains: list[str] = field(default_factory=list)
    status: str = "stub"
    created: str | None = None
    updated: str | None = None
    sources: list[str] = field(default_factory=list)
    relationships: list[Relationship] = field(default_factory=list)
    body: str = ""


def parse(raw_text: str) -> ParsedConcept:
    lines = raw_text.splitlines()
    if not lines or lines[0].strip() != _DELIMITER:
        raise FrontmatterError("file does not start with a '---' frontmatter block")

    try:
        end_index = lines.index(_DELIMITER, 1)
    except ValueError as exc:
        raise FrontmatterError("frontmatter block is not closed with '---'") from exc

    frontmatter_text = "\n".join(lines[1:end_index])
    body = "\n".join(lines[end_index + 1 :]).lstrip("\n")

    try:
        data = yaml.safe_load(frontmatter_text) or {}
    except yaml.YAMLError as exc:
        raise FrontmatterError(f"invalid YAML: {exc}") from exc

    if not isinstance(data, dict) or "id" not in data or "title" not in data:
        raise FrontmatterError("frontmatter must include 'id' and 'title'")

    relationships = [
        Relationship(type=r["type"], target=r["target"], note=r.get("note"))
        for r in (data.get("relationships") or [])
    ]

    return ParsedConcept(
        id=str(data["id"]),
        title=str(data["title"]),
        aliases=list(data.get("aliases") or []),
        domains=list(data.get("domains") or []),
        status=data.get("status") or "stub",
        created=_as_str(data.get("created")),
        updated=_as_str(data.get("updated")),
        sources=list(data.get("sources") or []),
        relationships=relationships,
        body=body,
    )


def _as_str(value: object) -> str | None:
    # YAML parses unquoted dates like `2026-09-22` as datetime.date, not str.
    return None if value is None else str(value)

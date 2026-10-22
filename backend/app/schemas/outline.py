"""The outline tree an ingest job proposes, and its structural validation."""

from typing import Literal

import re

from pydantic import BaseModel, Field

from app.vault.titles import InvalidTitleError, sanitize_title, title_key


_KEY_PATTERN = re.compile(r"[A-Za-z0-9_.-]{1,40}")


class OverlapVerdict(BaseModel):
    kind: Literal["same", "partial", "distinct"]
    target_note_id: str | None = None
    reason: str = ""


class OutlineNode(BaseModel):
    key: str
    title: str
    summary: str = ""
    parent_keys: list[str] = Field(default_factory=list)
    domains: list[str] = Field(default_factory=list)  # domain slugs; empty until the job fills in the resolved domains
    content_slice: str | None = None  # content-given mode: the part of the input that belongs to this node
    verdicts: dict[str, OverlapVerdict] = Field(default_factory=dict)  # keyed by domain slug


class Outline(BaseModel):
    topic_title: str
    nodes: list[OutlineNode]


def validate_outline(outline: Outline, *, max_nodes: int = 40, max_depth: int = 5) -> list[str]:
    """Human-readable problems with the tree; empty means valid."""
    errors: list[str] = []
    nodes = outline.nodes
    if not nodes:
        return ["the outline has no nodes"]
    if len(nodes) > max_nodes:
        errors.append(f"the outline has {len(nodes)} nodes; the limit is {max_nodes}")

    keys = [n.key for n in nodes]
    bad_keys = [k for k in keys if not _KEY_PATTERN.fullmatch(k)]
    if bad_keys:
        errors.append(f"node keys may only use letters, digits, '_', '-' and '.' (max 40 characters); fix {bad_keys}")
    if len(set(keys)) != len(keys):
        errors.append("node keys must be unique")
    by_key = {n.key: n for n in nodes}

    seen_titles: dict[str, str] = {}
    for n in nodes:
        try:
            clean = sanitize_title(n.title)
        except InvalidTitleError:
            errors.append(f"node {n.key!r} has an empty or unusable title")
            continue
        if title_key(clean) in seen_titles:
            errors.append(f"nodes {seen_titles[title_key(clean)]!r} and {n.key!r} have the same title {clean!r}")
        seen_titles[title_key(clean)] = n.key
        for parent in n.parent_keys:
            if parent not in by_key:
                errors.append(f"node {n.key!r} names an unknown parent {parent!r}")
            elif parent == n.key:
                errors.append(f"node {n.key!r} is its own parent")

    roots = [n.key for n in nodes if not n.parent_keys]
    if len(roots) != 1:
        errors.append(f"the outline must have exactly one root node (no parent), found {len(roots)}: {roots}")

    if not errors:
        errors += _cycle_or_depth_errors(by_key, max_depth)
    return errors


def _cycle_or_depth_errors(by_key: dict[str, OutlineNode], max_depth: int) -> list[str]:
    depth: dict[str, int] = {}

    def depth_of(key: str, path: tuple[str, ...]) -> int | None:
        if key in path:
            return None  # cycle
        if key in depth:
            return depth[key]
        parents = by_key[key].parent_keys
        if not parents:
            depth[key] = 1
            return 1
        parent_depths = [depth_of(p, path + (key,)) for p in parents]
        if any(d is None for d in parent_depths):
            return None
        depth[key] = 1 + max(parent_depths)  # type: ignore[type-var]
        return depth[key]

    for key in by_key:
        d = depth_of(key, ())
        if d is None:
            return [f"the outline contains a cycle through node {key!r}"]
        if d > max_depth:
            return [f"node {key!r} is {d} levels deep; the limit is {max_depth}"]
    return []

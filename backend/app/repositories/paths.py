"""Path resolution and traversal guards.

The only function allowed to turn user-supplied path segments into a real
filesystem path. Every repository call goes through `resolve_within` so a
malformed `category`/`filename`/`slug` can never escape the directory it's
supposed to be confined to.
"""

from pathlib import Path


class PathTraversalError(ValueError):
    """A requested path would escape its configured root."""


def resolve_within(root: Path, *segments: str) -> Path:
    """Resolve `segments` (each may itself contain `/`) against `root`.

    Rejects empty/`.`/`..` components and anything that resolves outside
    `root`, including via symlinks.
    """
    root = root.resolve()
    candidate = root

    for segment in segments:
        for part in segment.split("/"):
            if part in ("", ".", ".."):
                raise PathTraversalError(f"invalid path segment: {part!r}")
            candidate = candidate / part

    resolved = candidate.resolve()
    if resolved != root and root not in resolved.parents:
        raise PathTraversalError(f"path escapes root: {resolved}")

    return resolved

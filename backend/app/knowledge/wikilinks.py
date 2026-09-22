"""Extract `[[wikilink]]` targets from a knowledge concept's body text.
Pure function — see docs/ARCHITECTURE.md §14.2.
"""

import re

_WIKILINK_PATTERN = re.compile(r"\[\[([^\]]+)\]\]")


def extract_links(body: str) -> list[str]:
    """Slugs referenced via `[[slug]]` (or `[[slug|display text]]`) in the
    body, in order of first appearance, deduplicated."""
    seen: dict[str, None] = {}
    for match in _WIKILINK_PATTERN.finditer(body):
        slug = match.group(1).split("|", 1)[0].strip()
        if slug:
            seen.setdefault(slug, None)
    return list(seen)

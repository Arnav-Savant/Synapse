"""The vault map the navigator reasons over (ARCHITECTURE §12.4).

Built from the note index each time it is asked for, so it is never stale and
is not stored. Every note appears once, as a tree under its first parent.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import domain_repo, note_index_repo
from app.repositories.note_index_repo import MapRow
from app.schemas.chat_agents import VaultMap
from app.vault.titles import title_key

logger = logging.getLogger(__name__)


def _line(row: MapRow, extra_parents: list[str], depth: int) -> str:
    summary = " ".join(row.summary.split())
    line = f"{'  ' * depth}- {row.title}" + (f": {summary}" if summary else "")
    related = sorted({t for t in row.related}, key=str.lower)
    if related:
        line += f"  [related: {', '.join(related)}]"
    if extra_parents:
        line += f" (also under {', '.join(extra_parents)})"
    return line


def _render_domain(slug: str, rows: list[MapRow]) -> str:
    if not rows:
        return f"# {slug}\n(no notes yet)"
    by_key = {title_key(r.title): r for r in rows}
    # A parent that isn't indexed counts as no parent.
    parents: dict[str, list[str]] = {}
    for key, row in by_key.items():
        found = {title_key(p) for p in row.parents if title_key(p) in by_key}
        parents[key] = sorted(found, key=lambda k: by_key[k].title.lower())
    children: dict[str, list[str]] = {key: [] for key in by_key}
    for key, above in parents.items():
        if above:
            children[above[0]].append(key)
    for kids in children.values():
        kids.sort(key=lambda k: by_key[k].title.lower())

    lines: list[str] = []
    seen: set[str] = set()

    def walk(start: str) -> None:
        stack = [(start, 0)]
        while stack:
            key, depth = stack.pop()
            if key in seen:
                continue
            seen.add(key)
            extra = [by_key[k].title for k in parents[key][1:]]
            lines.append(_line(by_key[key], extra, depth))
            stack.extend((kid, depth + 1) for kid in reversed(children[key]))

    ordered = sorted(by_key, key=lambda k: by_key[k].title.lower())
    for key in ordered:
        if not parents[key]:
            walk(key)
    for key in ordered:  # notes left over sit on a cycle: list one at the top level to break it
        if key not in seen:
            walk(key)
    return f"# {slug}\n" + "\n".join(lines)


async def build_vault_map(session: AsyncSession, domain_slugs: list[str]) -> VaultMap:
    """Domains that no longer exist are skipped."""
    sections: list[str] = []
    keys: dict[str, set[str]] = {}
    for slug in domain_slugs:
        try:
            domain = await domain_repo.get_by_slug(session, slug)
        except domain_repo.DomainNotFoundError:
            logger.info("vault map skipped a domain that no longer exists: slug=%s", slug)
            continue
        rows = await note_index_repo.map_rows(session, domain.id)
        keys[slug] = {title_key(r.title) for r in rows}
        sections.append(_render_domain(slug, rows))
    return VaultMap(text="\n\n".join(sections), keys=keys)

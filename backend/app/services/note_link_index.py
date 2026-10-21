"""Rebuilds one note's `note_links` rows from its file text.

Link kinds: `parent` (frontmatter `parents`), `related` (inside `## Related`),
`body` (every other wikilink; the `Up:` line is skipped because it repeats
`parents`). Used wherever a note file changes: delete, reconcile, commit.
"""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Note
from app.repositories import note_index_repo
from app.vault.assemble import section_span
from app.vault.frontmatter import FrontmatterError, split_frontmatter
from app.vault.titles import title_key
from app.vault.wikilinks import find_wikilinks

logger = logging.getLogger(__name__)


def parent_titles_from_text(text: str) -> list[str]:
    """Parent titles from the frontmatter `parents` list; empty if there is none or it is unreadable."""
    try:
        meta, _ = split_frontmatter(text)
    except FrontmatterError:
        return []
    titles: list[str] = []
    for item in meta.get("parents") or []:
        links = find_wikilinks(str(item))
        if links and links[0].target and links[0].target not in titles:
            titles.append(links[0].target)
    return titles


async def reindex_note_links(session: AsyncSession, note: Note, text: str) -> None:
    try:
        _, body = split_frontmatter(text)
    except FrontmatterError:
        logger.warning("note %r has unreadable frontmatter; indexing its body links only", note.title)
        body = text

    wanted: list[tuple[str, str]] = [(t, "parent") for t in parent_titles_from_text(text)]
    related = section_span(body, "Related")
    for link in find_wikilinks(body):
        if not link.target:
            continue  # [[#heading]] points inside the note itself
        line_start = body.rfind("\n", 0, link.start) + 1
        if body[line_start : link.start].lstrip().startswith("Up:"):
            continue
        in_related = related is not None and related[0] <= link.start < related[1]
        wanted.append((link.target, "related" if in_related else "body"))

    rows: list[tuple[str | None, str, str]] = []
    seen: set[tuple[str, str]] = set()
    for target, kind in wanted:
        key = (title_key(target), kind)
        if key in seen or key[0] == title_key(note.title):
            continue
        seen.add(key)
        dst = await note_index_repo.find_by_title_key(session, note.domain_id, target)
        rows.append((dst.synapse_id if dst else None, target, kind))
    await note_index_repo.replace_links(session, note.synapse_id, rows)

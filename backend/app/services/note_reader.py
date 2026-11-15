"""Read-only access to note text for the chat agents (ARCHITECTURE §12.4).

Agents never supply a path: they name a note by `(domain, title)`, and the path
comes from the index and goes through `resolve_in_vault`. Text is always the
file as it is now, so the owner's latest edits are used. Nothing here writes.
"""

import asyncio
import logging
import re
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import domain_repo, note_index_repo
from app.schemas.chat_agents import NoteText, SearchHit
from app.vault.frontmatter import FrontmatterError, split_frontmatter
from app.vault.paths import VaultPathError, resolve_in_vault

logger = logging.getLogger(__name__)

SNIPPET_CHARS = 300
_HEADING = re.compile(r"^#{1,6}[ \t]+(.+?)[ \t#]*$", re.MULTILINE)


class NoteUnavailableError(LookupError):
    """A note the agent asked for cannot be read right now."""


def _body(text: str) -> str:
    try:
        return split_frontmatter(text)[1]
    except FrontmatterError:
        return text  # broken frontmatter: the owner still wants the note read


async def read_note(session: AsyncSession, domain_slug: str, title: str) -> NoteText:
    unavailable = NoteUnavailableError(f"{title} ({domain_slug}) was not found; a rescan may help")
    try:
        domain = await domain_repo.get_by_slug(session, domain_slug)
    except domain_repo.DomainNotFoundError as exc:
        raise unavailable from exc
    note = await note_index_repo.find_by_title_key(session, domain.id, title)
    if note is None:
        raise unavailable
    try:
        path = resolve_in_vault(Path(domain.vault_path), *note.path.split("/"))
        text = await asyncio.to_thread(path.read_text, encoding="utf-8")
    except (VaultPathError, OSError, UnicodeDecodeError) as exc:
        logger.info("note could not be read for chat: domain=%s note_id=%s", domain_slug, note.synapse_id)
        raise unavailable from exc
    return NoteText(domain=domain_slug, title=note.title, note_id=note.synapse_id, text=_body(text))


def _snippet(body: str, start: int, end: int) -> str:
    centre = (start + end) // 2
    window = body[max(0, centre - SNIPPET_CHARS // 2) : centre + SNIPPET_CHARS // 2]
    return " ".join(window.split())


def _scan_vault(slug: str, root: Path, titles: dict[str, str], patterns: list[re.Pattern[str]], limit: int) -> list[SearchHit]:
    hits: list[SearchHit] = []
    for path in sorted(root.rglob("*.md")):
        rel = path.relative_to(root)
        if any(part.startswith(".") for part in rel.parts):
            continue
        try:
            body = _body(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeDecodeError):
            continue
        title = titles.get(rel.as_posix(), path.stem)
        for pattern in patterns:
            match = pattern.search(body)
            if match is None:
                continue
            headings = [m.group(1) for m in _HEADING.finditer(body, 0, match.start())]
            hits.append(SearchHit(domain=slug, title=title, heading=headings[-1] if headings else "", snippet=_snippet(body, match.start(), match.end())))
            if len(hits) >= limit:
                return hits
    return hits


async def search_vault(session: AsyncSession, domain_slugs: list[str], terms: list[str], limit: int = 20) -> list[SearchHit]:
    patterns = [re.compile(re.escape(t.strip()), re.IGNORECASE) for t in terms if t.strip()]
    hits: list[SearchHit] = []
    if not patterns:
        return hits
    for slug in domain_slugs:
        if len(hits) >= limit:
            break
        try:
            domain = await domain_repo.get_by_slug(session, slug)
        except domain_repo.DomainNotFoundError:
            continue
        titles = {n.path: n.title for n in await note_index_repo.list_notes(session, domain.id)}
        hits += await asyncio.to_thread(_scan_vault, slug, Path(domain.vault_path), titles, patterns, limit - len(hits))
    return hits

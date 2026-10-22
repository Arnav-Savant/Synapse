"""Hub placement: what a vault offers to attach a topic to, and whether a chosen placement is valid."""

from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories import domain_repo, note_index_repo
from app.schemas.outline import Outline
from app.schemas.placement import HubInfo, NoteBrief, check_adopted, check_ancestors
from app.vault.titles import sanitize_title, title_key


async def load_options(session: AsyncSession, domain_id: str) -> tuple[list[HubInfo], list[NoteBrief]]:
    """The hubs in a vault (with the hub each sits under) and the top-level notes not under any hub."""
    hubs = [
        HubInfo(id=h.synapse_id, title=h.title, summary=h.summary, parent_title=parent)
        for h, parent in await note_index_repo.list_hubs(session, domain_id)
    ]
    notes = [
        NoteBrief(id=n.synapse_id, title=n.title, summary=n.summary)
        for n in await note_index_repo.list_top_level_notes(session, domain_id)
    ]
    return hubs, notes


async def validate_placement(session: AsyncSession, outline: Outline) -> list[str]:
    """Problems with the hub paths and attachments in an outline; empty means valid."""
    errors: list[str] = []
    node_titles = {title_key(n.title) for n in outline.nodes}
    for slug in sorted(set(outline.ancestors) | set(outline.adopt)):
        try:
            domain = await domain_repo.get_by_slug(session, slug)
        except domain_repo.DomainNotFoundError:
            errors.append(f"there is no domain {slug!r}")
            continue
        hubs, orphans = await load_options(session, domain.id)
        ancestors = outline.ancestors.get(slug, [])
        errors += [f"{slug}: {e}" for e in check_ancestors(ancestors, hubs)]
        errors += [f"{slug}: {e}" for e in check_adopted(outline.adopt.get(slug, []), ancestors, orphans)]
        for a in ancestors:
            if a.existing_note_id:
                continue
            try:
                key = title_key(sanitize_title(a.title))
            except ValueError:
                continue  # already reported by check_ancestors
            clash = await note_index_repo.find_by_title_key(session, domain.id, a.title)
            if clash is not None:
                errors.append(f"{slug}: a note titled {a.title!r} already exists, so it cannot also be a new hub")
            if key in node_titles:
                errors.append(f"{slug}: the new hub {a.title!r} has the same title as a note in the outline")
    return errors

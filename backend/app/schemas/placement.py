"""Where a topic sits above its top note: the hub levels, and which existing notes get attached under them.

Pure rules, shared by the agent that proposes a placement and by the check on the owner's own edits.
"""

from pydantic import BaseModel

from app.schemas.outline import MAX_HUB_LEVELS, Ancestor
from app.vault.titles import InvalidTitleError, sanitize_title, title_key

MAX_ADOPTED = 8


class HubInfo(BaseModel):
    """A hub that already exists in a vault."""

    id: str
    title: str
    summary: str = ""
    parent_title: str | None = None  # the hub it sits under, if any


class NoteBrief(BaseModel):
    """An existing top-level note that could be attached under a hub."""

    id: str
    title: str
    summary: str = ""


def check_ancestors(ancestors: list[Ancestor], hubs: list[HubInfo]) -> list[str]:
    """What is wrong with a hub path (outermost first); empty means it is valid."""
    errors: list[str] = []
    if len(ancestors) > MAX_HUB_LEVELS:
        errors.append(f"at most {MAX_HUB_LEVELS} hub levels are allowed above a topic, got {len(ancestors)}")
    by_id = {h.id: h for h in hubs}
    seen: set[str] = set()
    previous: Ancestor | None = None
    for a in ancestors:
        try:
            clean = sanitize_title(a.title)
        except InvalidTitleError:
            errors.append("a hub has an empty or unusable title")
            continue
        key = title_key(clean)
        if key in seen:
            errors.append(f"the hub {clean!r} appears twice")
        seen.add(key)
        if a.existing_note_id:
            hub = by_id.get(a.existing_note_id)
            if hub is None:
                errors.append(f"{clean!r} is not an existing hub in this vault")
            elif title_key(hub.title) != key:
                errors.append(f"the title {clean!r} does not match the existing hub {hub.title!r}")
            if previous is not None and not previous.existing_note_id:
                errors.append(f"the existing hub {clean!r} cannot sit under the new hub {previous.title!r}")
            elif previous is not None and hub is not None and (hub.parent_title is None or title_key(hub.parent_title) != title_key(previous.title)):
                errors.append(f"the existing hub {clean!r} does not sit under {previous.title!r}")
        else:
            if any(title_key(h.title) == key for h in hubs):
                errors.append(f"a hub named {clean!r} already exists; reuse it instead of creating another")
        previous = a
    return errors


def check_adopted(note_ids: list[str], ancestors: list[Ancestor], candidates: list[NoteBrief]) -> list[str]:
    errors: list[str] = []
    if note_ids and not ancestors:
        errors.append("notes can only be attached under a hub, but this topic has none")
    if len(note_ids) > MAX_ADOPTED:
        errors.append(f"at most {MAX_ADOPTED} existing notes can be attached at once")
    valid = {c.id for c in candidates}
    for nid in note_ids:
        if nid not in valid:
            errors.append(f"note {nid!r} is not a top-level note that can be attached")
    return errors

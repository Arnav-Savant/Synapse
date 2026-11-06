"""Where a topic sits above its top note: the parent notes, and which existing notes get attached under them.

Pure rules, shared by the agent that proposes a placement and by the check on the owner's own edits.
"""

from pydantic import BaseModel

from app.schemas.outline import MAX_PARENT_LEVELS, Ancestor
from app.vault.titles import InvalidTitleError, sanitize_title, title_key

MAX_ADOPTED = 8


class ParentInfo(BaseModel):
    """An existing note that already has children, so a topic can be placed under it."""

    id: str
    title: str
    summary: str = ""
    parent_title: str | None = None  # the note it sits under, if any


class NoteBrief(BaseModel):
    """An existing top-level note that could be attached under a parent."""

    id: str
    title: str
    summary: str = ""


def check_ancestors(ancestors: list[Ancestor], parents: list[ParentInfo]) -> list[str]:
    """What is wrong with a chain of parent notes (outermost first); empty means it is valid."""
    errors: list[str] = []
    if len(ancestors) > MAX_PARENT_LEVELS:
        errors.append(f"at most {MAX_PARENT_LEVELS} parent levels are allowed above a topic, got {len(ancestors)}")
    by_id = {p.id: p for p in parents}
    seen: set[str] = set()
    previous: Ancestor | None = None
    for a in ancestors:
        try:
            clean = sanitize_title(a.title)
        except InvalidTitleError:
            errors.append("a parent has an empty or unusable title")
            continue
        key = title_key(clean)
        if key in seen:
            errors.append(f"the parent {clean!r} appears twice")
        seen.add(key)
        if a.existing_note_id:
            parent = by_id.get(a.existing_note_id)
            if parent is None:
                errors.append(f"{clean!r} is not an existing parent note in this vault")
            elif title_key(parent.title) != key:
                errors.append(f"the title {clean!r} does not match the existing parent {parent.title!r}")
            if previous is not None and not previous.existing_note_id:
                errors.append(f"the existing parent {clean!r} cannot sit under the new parent {previous.title!r}")
            elif previous is not None and parent is not None and (parent.parent_title is None or title_key(parent.parent_title) != title_key(previous.title)):
                errors.append(f"the existing parent {clean!r} does not sit under {previous.title!r}")
        else:
            if any(title_key(p.title) == key for p in parents):
                errors.append(f"a note named {clean!r} already has children; reuse it instead of creating another")
        previous = a
    return errors


def check_adopted(note_ids: list[str], ancestors: list[Ancestor], candidates: list[NoteBrief]) -> list[str]:
    errors: list[str] = []
    if note_ids and not ancestors:
        errors.append("notes can only be attached under a parent, but this topic has none")
    if len(note_ids) > MAX_ADOPTED:
        errors.append(f"at most {MAX_ADOPTED} existing notes can be attached at once")
    valid = {c.id for c in candidates}
    above = {a.existing_note_id for a in ancestors if a.existing_note_id}
    for nid in note_ids:
        if nid in above:
            errors.append(f"note {nid!r} is one of the parents above the topic, so it cannot also be attached under them")
        elif nid not in valid:
            errors.append(f"note {nid!r} is not a top-level note that can be attached")
    return errors

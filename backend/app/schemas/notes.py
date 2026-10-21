from pydantic import BaseModel


class NoteRef(BaseModel):
    synapse_id: str
    title: str
    path: str  # relative to the domain's vault folder
    domain_slug: str
    user_modified: bool = False


class FileEdit(BaseModel):
    """A note that will be rewritten only to strip links to deleted notes."""

    note: NoteRef
    links_removed: int


class ReparentChange(BaseModel):
    """A child that loses a deleted parent and takes over that parent's own parents."""

    child: NoteRef
    new_parents: list[str]  # empty -> the child becomes top-level


class DeletePlan(BaseModel):
    delete_notes: list[NoteRef]
    edits: list[FileEdit]
    reparent: list[ReparentChange]
    needs_extra_confirm: list[NoteRef]  # deleted notes the owner has edited in Obsidian

from typing import Literal

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


class NoteOut(BaseModel):
    synapse_id: str
    title: str
    path: str
    summary: str
    domain_slug: str
    user_modified: bool
    job_id: str | None  # the job that created it; lets the owner delete everything one job made
    twin_domains: list[str]  # other vaults holding a note on the same subject


class NotesResponse(BaseModel):
    notes: list[NoteOut]


class DeleteSelector(BaseModel):
    """Exactly one of note_ids, topic_folder or job_id."""

    domain: str
    note_ids: list[str] | None = None
    topic_folder: str | None = None
    job_id: str | None = None
    twin_scope: Literal["this", "all"] = "this"


class DeleteRequest(DeleteSelector):
    confirm_modified: bool = False


class TidyEdit(BaseModel):
    """A note whose Related section would lose some entries."""

    note: NoteRef
    remove: list[str]  # entries the rules remove: they repeat the tree, or the pair is kept on the other note
    review: list[str] = []  # entries the link reviewer judged not essential; removed only if the owner confirms


class TidyPlan(BaseModel):
    domain_slug: str
    edits: list[TidyEdit]
    links: int
    reviewed: bool  # true when the agent review ran
    cost_usd: float


class TidyRemoval(BaseModel):
    note_id: str
    titles: list[str]


class TidyRequest(BaseModel):
    domain_slug: str
    extra: list[TidyRemoval] = []  # reviewed entries the owner confirmed, on top of the rule-based ones


class TidyResult(BaseModel):
    notes_changed: int
    links_removed: int


class DeleteResponse(BaseModel):
    deleted: int
    links_stripped_in: int
    children_reattached: int


class ReconcileOut(BaseModel):
    removed: int
    added: int
    modified: int
    moved: int


class ReconcileResponse(BaseModel):
    domains: dict[str, ReconcileOut]

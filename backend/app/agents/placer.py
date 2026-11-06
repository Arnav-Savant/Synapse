"""Placer: decides which parent note(s) a new topic sits under, and which existing top-level notes belong beside it."""

import logging

from pydantic import BaseModel, Field, model_validator

from app.agents.runner import RunResult, run_structured
from app.engines.base import AgentEngine
from app.schemas.outline import MAX_PARENT_LEVELS, Ancestor, OutlineNode
from app.schemas.placement import MAX_ADOPTED, NoteBrief, ParentInfo, check_ancestors
from app.vault.titles import title_key

logger = logging.getLogger(__name__)


class PlacedParent(BaseModel):
    title: str
    existing: bool = Field(description="true to reuse a parent note from the list, copying its title exactly")
    summary: str = Field(default="", description="one line on what the parent covers; required for a new parent")


class Placement(BaseModel):
    parents: list[PlacedParent] = Field(default_factory=list, description="outermost first; empty when the topic stands alone")
    attach: list[str] = Field(default_factory=list, description="titles of existing top-level notes that belong beside this topic")
    reason: str = ""


def _placement_model(parents: list[ParentInfo], notes: list[NoteBrief]) -> type[Placement]:
    """The Placement schema with this vault's rules attached, so a bad choice becomes a specific re-ask."""
    parent_by_key = {title_key(p.title): p for p in parents}
    note_keys = {title_key(n.title) for n in notes}

    class _Placement(Placement):
        @model_validator(mode="after")
        def _valid(self) -> "_Placement":
            problems = check_ancestors(_to_ancestors(self.parents, parent_by_key), parents)
            for p in self.parents:
                if not p.existing and not p.summary.strip():
                    problems.append(f"the new parent {p.title!r} needs a one-line summary")
                if p.existing and title_key(p.title) not in parent_by_key:
                    problems.append(f"{p.title!r} is not in the list of existing parent notes")
            if self.attach and not self.parents:
                problems.append("`attach` must be empty when there is no parent")
            if len(self.attach) > MAX_ADOPTED:
                problems.append(f"attach at most {MAX_ADOPTED} notes")
            problems += [f"{t!r} is not in the list of top-level notes" for t in self.attach if title_key(t) not in note_keys]
            above = {title_key(p.title) for p in self.parents}
            problems += [f"{t!r} is one of the parents; it cannot also be attached" for t in self.attach if title_key(t) in above]
            if problems:
                raise ValueError("; ".join(problems))
            return self

    return _Placement


def _to_ancestors(placed: list[PlacedParent], parent_by_key: dict[str, ParentInfo]) -> list[Ancestor]:
    out: list[Ancestor] = []
    for p in placed:
        existing = parent_by_key.get(title_key(p.title)) if p.existing else None
        out.append(Ancestor(title=existing.title if existing else p.title.strip(), summary=p.summary.strip() or (existing.summary if existing else ""), existing_note_id=existing.id if existing else None))
    return out


def _parent_tree(parents: list[ParentInfo]) -> str:
    if not parents:
        return "(none yet)"
    children: dict[str | None, list[ParentInfo]] = {}
    titles = {title_key(p.title) for p in parents}
    for p in parents:
        above = p.parent_title if p.parent_title and title_key(p.parent_title) in titles else None
        children.setdefault(above and title_key(above), []).append(p)
    lines: list[str] = []

    def walk(above_key: str | None, depth: int) -> None:
        for p in children.get(above_key, []):
            lines.append(f"{'  ' * depth}- {p.title}: {p.summary or '(no summary)'}")
            walk(title_key(p.title), depth + 1)

    walk(None, 0)
    return "\n".join(lines)


async def place_topic(
    engine: AgentEngine,
    *,
    job_id: str,
    domain_name: str,
    domain_purpose: str,
    root: OutlineNode,
    subtopics: list[str],
    parents: list[ParentInfo],
    notes: list[NoteBrief],
) -> RunResult[tuple[list[Ancestor], list[NoteBrief]]]:
    """Returns the parent chain (outermost first, possibly empty) and the existing notes to attach under the innermost parent."""
    model_cls = _placement_model(parents, notes)
    note_lines = "\n".join(f"- {n.title}: {n.summary or '(no summary)'}" for n in notes) or "(none)"
    prompt = (
        "You decide where a new study topic sits in the notebook of one knowledge domain.\n\n"
        f"Domain: {domain_name}. {domain_purpose}\n\n"
        f"New topic: {root.title}\nWhat it covers: {root.summary}\nIts subtopics: {', '.join(subtopics) or '(none)'}\n\n"
        f"Existing notes that already have children (nested ones sit under the note above them):\n{_parent_tree(parents)}\n\n"
        f"Existing top-level notes (no parent):\n{note_lines}\n\n"
        "A parent note is a short overview that groups related topics in one area, for example 'Database internals' "
        "groups topics such as write-ahead logging, buffer pools and B-trees. Choose where this topic belongs:\n"
        f"- Use as few parent levels as make sense: 0, 1 or {MAX_PARENT_LEVELS}, never more than {MAX_PARENT_LEVELS}. Zero is right when the "
        "topic stands alone or is broad enough to be top-level.\n"
        "- ALWAYS reuse an existing parent when one fits: set existing=true and copy its title exactly. Create a new parent "
        "(existing=false, with a plain noun-phrase title and a one-line summary) only when no existing note fits and the "
        "topic clearly belongs to a broader area that would hold several topics. Never create a parent just to wrap one topic.\n"
        "- List parents outermost first. An existing parent can only sit under another existing parent; a new parent may sit under "
        "an existing one.\n"
        f"- `attach`: titles of existing top-level notes (from the list above) that clearly belong in the same area as the "
        f"innermost parent you chose, at most {MAX_ADOPTED}. Leave it empty when there is no parent or nothing fits."
    )
    result = await run_structured(engine, role="placer", job_id=job_id, prompt=prompt, model_cls=model_cls)
    parent_by_key = {title_key(p.title): p for p in parents}
    note_by_key = {title_key(n.title): n for n in notes}
    ancestors = _to_ancestors(result.value.parents, parent_by_key)
    attach = [note_by_key[title_key(t)] for t in dict.fromkeys(result.value.attach)]
    logger.info(
        "job %s: %r placed under %s%s", job_id[:8], root.title,
        " > ".join(a.title + ("" if a.existing_note_id else " (new)") for a in ancestors) or "no parent",
        f", attaching {len(attach)} existing note(s)" if attach else "",
    )
    return RunResult(value=(ancestors, attach), cost_usd=result.cost_usd, fetched_urls=result.fetched_urls)

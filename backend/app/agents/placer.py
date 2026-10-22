"""Placer: decides which hub(s) a new topic sits under, and which existing top-level notes belong beside it."""

import logging

from pydantic import BaseModel, Field, model_validator

from app.agents.runner import RunResult, run_structured
from app.engines.base import AgentEngine
from app.schemas.outline import MAX_HUB_LEVELS, Ancestor, OutlineNode
from app.schemas.placement import MAX_ADOPTED, HubInfo, NoteBrief, check_ancestors
from app.vault.titles import title_key

logger = logging.getLogger(__name__)


class PlacedHub(BaseModel):
    title: str
    existing: bool = Field(description="true to reuse a hub from the list, copying its title exactly")
    summary: str = Field(default="", description="one line on what the hub covers; required for a new hub")


class Placement(BaseModel):
    hubs: list[PlacedHub] = Field(default_factory=list, description="outermost first; empty when the topic stands alone")
    attach: list[str] = Field(default_factory=list, description="titles of existing top-level notes that belong beside this topic")
    reason: str = ""


def _placement_model(hubs: list[HubInfo], notes: list[NoteBrief]) -> type[Placement]:
    """The Placement schema with this vault's rules attached, so a bad choice becomes a specific re-ask."""
    hub_by_key = {title_key(h.title): h for h in hubs}
    note_keys = {title_key(n.title) for n in notes}

    class _Placement(Placement):
        @model_validator(mode="after")
        def _valid(self) -> "_Placement":
            problems = check_ancestors(_to_ancestors(self.hubs, hub_by_key), hubs)
            for h in self.hubs:
                if not h.existing and not h.summary.strip():
                    problems.append(f"the new hub {h.title!r} needs a one-line summary")
                if h.existing and title_key(h.title) not in hub_by_key:
                    problems.append(f"{h.title!r} is not in the list of existing hubs")
            if self.attach and not self.hubs:
                problems.append("`attach` must be empty when there is no hub")
            if len(self.attach) > MAX_ADOPTED:
                problems.append(f"attach at most {MAX_ADOPTED} notes")
            problems += [f"{t!r} is not in the list of top-level notes" for t in self.attach if title_key(t) not in note_keys]
            if problems:
                raise ValueError("; ".join(problems))
            return self

    return _Placement


def _to_ancestors(placed: list[PlacedHub], hub_by_key: dict[str, HubInfo]) -> list[Ancestor]:
    out: list[Ancestor] = []
    for h in placed:
        existing = hub_by_key.get(title_key(h.title)) if h.existing else None
        out.append(Ancestor(title=existing.title if existing else h.title.strip(), summary=h.summary.strip() or (existing.summary if existing else ""), existing_note_id=existing.id if existing else None))
    return out


def _hub_tree(hubs: list[HubInfo]) -> str:
    if not hubs:
        return "(none yet)"
    children: dict[str | None, list[HubInfo]] = {}
    titles = {title_key(h.title) for h in hubs}
    for h in hubs:
        parent = h.parent_title if h.parent_title and title_key(h.parent_title) in titles else None
        children.setdefault(parent and title_key(parent), []).append(h)
    lines: list[str] = []

    def walk(parent_key: str | None, depth: int) -> None:
        for h in children.get(parent_key, []):
            lines.append(f"{'  ' * depth}- {h.title}: {h.summary or '(no summary)'}")
            walk(title_key(h.title), depth + 1)

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
    hubs: list[HubInfo],
    notes: list[NoteBrief],
) -> RunResult[tuple[list[Ancestor], list[NoteBrief]]]:
    """Returns the hub path (outermost first, possibly empty) and the existing notes to attach under the innermost hub."""
    model_cls = _placement_model(hubs, notes)
    note_lines = "\n".join(f"- {n.title}: {n.summary or '(no summary)'}" for n in notes) or "(none)"
    prompt = (
        "You decide where a new study topic sits in the notebook of one knowledge domain.\n\n"
        f"Domain: {domain_name}. {domain_purpose}\n\n"
        f"New topic: {root.title}\nWhat it covers: {root.summary}\nIts subtopics: {', '.join(subtopics) or '(none)'}\n\n"
        f"Hubs that already exist (nested ones sit under the hub above them):\n{_hub_tree(hubs)}\n\n"
        f"Existing top-level notes that are not under any hub:\n{note_lines}\n\n"
        "A hub is a short overview note that groups related topics in one area, for example 'Database internals' "
        "groups topics such as write-ahead logging, buffer pools and B-trees. Choose where this topic belongs:\n"
        f"- Use as few hub levels as make sense: 0, 1 or {MAX_HUB_LEVELS}, never more than {MAX_HUB_LEVELS}. Zero is right when the "
        "topic stands alone or is broad enough to be top-level.\n"
        "- ALWAYS reuse an existing hub when one fits: set existing=true and copy its title exactly. Create a new hub "
        "(existing=false, with a plain noun-phrase title and a one-line summary) only when no existing hub fits and the "
        "topic clearly belongs to a broader area that would hold several topics. Never create a hub just to wrap one topic.\n"
        "- List hubs outermost first. An existing hub can only sit under another existing hub; a new hub may sit under "
        "an existing one.\n"
        f"- `attach`: titles of existing top-level notes (from the list above) that clearly belong in the same area as the "
        f"innermost hub you chose, at most {MAX_ADOPTED}. Leave it empty when there is no hub or nothing fits."
    )
    result = await run_structured(engine, role="placer", job_id=job_id, prompt=prompt, model_cls=model_cls)
    hub_by_key = {title_key(h.title): h for h in hubs}
    note_by_key = {title_key(n.title): n for n in notes}
    ancestors = _to_ancestors(result.value.hubs, hub_by_key)
    attach = [note_by_key[title_key(t)] for t in dict.fromkeys(result.value.attach)]
    logger.info(
        "job %s: %r placed under %s%s", job_id[:8], root.title,
        " > ".join(a.title + ("" if a.existing_note_id else " (new)") for a in ancestors) or "no hub",
        f", attaching {len(attach)} existing note(s)" if attach else "",
    )
    return RunResult(value=(ancestors, attach), cost_usd=result.cost_usd, fetched_urls=result.fetched_urls)

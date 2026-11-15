"""Plain data the chat agents are given and the chat runtime gathers.

These live in schemas because agents take them as input and agents must not
import services.
"""

import json
from dataclasses import dataclass

from pydantic import BaseModel, Field


@dataclass(frozen=True)
class VaultMap:
    """`text` is the map shown to the navigator; `keys` maps a domain slug to the
    `title_key` of every note in that domain, for checking that a pick is a real note."""

    text: str
    keys: dict[str, set[str]]


@dataclass(frozen=True)
class NoteText:
    """A note as it is on disk now; `text` is the body without frontmatter."""

    domain: str
    title: str
    note_id: str
    text: str


@dataclass(frozen=True)
class SearchHit:
    domain: str
    title: str
    heading: str
    snippet: str


class NoteRef(BaseModel):
    domain: str
    title: str


class Pick(NoteRef):
    reason: str


class Passage(NoteRef):
    heading: str = Field(description="the heading the excerpt sits under, or an empty string")
    excerpt: str = Field(min_length=1)


@dataclass(frozen=True)
class ToolRecord:
    """One action an agent took in a run and what the runtime gave back."""

    action: str
    arguments: dict
    result: str


def log_block(log: list[ToolRecord]) -> str:
    """The run's log as numbered `action(arguments) → result` entries, resent because calls keep no session."""
    if not log:
        return "(nothing yet)"
    return "\n".join(
        f"{i}. {r.action}({json.dumps(r.arguments, ensure_ascii=False)}) → {r.result}" for i, r in enumerate(log, 1)
    )

"""Plain data the chat agents are given and the chat runtime gathers.

These live in schemas because agents take them as input and agents must not
import services.
"""

from dataclasses import dataclass


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

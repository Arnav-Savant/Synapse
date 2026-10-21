"""Note title handling: deterministic sanitizing and case-insensitive keys.

Titles become file names and `[[wikilink]]` targets, so characters Obsidian
rejects are removed, and uniqueness is judged on `title_key`, never on the
raw string.
"""

import re
import unicodedata

MAX_TITLE_LENGTH = 120

# Characters Obsidian rejects in file names or link targets.
_FORBIDDEN = re.compile(r'[\\/:*?"<>|#^\[\]]')
_CONTROL = re.compile(r"[\x00-\x1f\x7f]")
_WHITESPACE = re.compile(r"\s+")


class InvalidTitleError(ValueError):
    """A title is empty once sanitized, so no usable file name can be built from it."""


def sanitize_title(raw: str) -> str:
    title = unicodedata.normalize("NFC", raw)
    title = _FORBIDDEN.sub("", title)
    title = _CONTROL.sub(" ", title)
    title = _WHITESPACE.sub(" ", title).strip(" .")
    title = title[:MAX_TITLE_LENGTH].strip(" .")
    if not title:
        raise InvalidTitleError(f"title {raw!r} has nothing left after removing characters that are not allowed in note names")
    return title


def title_key(title: str) -> str:
    """Case-insensitive, Unicode-normalized identity of a title within a vault."""
    return unicodedata.normalize("NFC", title).casefold()

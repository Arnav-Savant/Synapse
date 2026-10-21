"""A small real wikilink parser (spec §20.5), not regexes over raw text.

Understands `[[X]]`, `[[X|alias]]`, `[[X#heading]]` and `[[X#^block]]`, and
never looks inside fenced code blocks or inline code. Links inside markdown
tables are handled: removal turns them into plain text, so the row keeps its
column structure.
"""

import re
from dataclasses import dataclass

from app.vault.titles import title_key

_FENCE_OPEN = re.compile(r"^ {0,3}(`{3,}|~{3,})(.*)$")
_BULLET_PREFIX = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+$")


@dataclass(frozen=True)
class WikiLink:
    target: str
    alias: str | None
    heading: str | None
    start: int  # index of the opening "[["
    end: int  # index just past the closing "]]"


def find_code_ranges(text: str) -> list[tuple[int, int]]:
    """Half-open (start, end) ranges covered by fenced code blocks or inline code."""
    ranges: list[tuple[int, int]] = []
    fence: tuple[str, int, int] | None = None  # (char, length, start offset)
    paragraph_start: int | None = None
    paragraph_end = 0
    offset = 0

    def flush_paragraph() -> None:
        nonlocal paragraph_start
        if paragraph_start is not None:
            ranges.extend(_inline_code_ranges(text, paragraph_start, paragraph_end))
            paragraph_start = None

    for line in text.splitlines(keepends=True):
        line_start, line_end = offset, offset + len(line)
        offset = line_end
        body = line.rstrip("\r\n")

        if fence is not None:
            char, length, fence_start = fence
            stripped = body.strip()
            if stripped and set(stripped) == {char} and len(stripped) >= length:
                ranges.append((fence_start, line_end))
                fence = None
            continue

        opener = _FENCE_OPEN.match(body)
        if opener and not (opener.group(1)[0] == "`" and "`" in opener.group(2)):
            flush_paragraph()
            fence = (opener.group(1)[0], len(opener.group(1)), line_start)
            continue

        if body.strip() == "":
            flush_paragraph()
            continue
        if paragraph_start is None:
            paragraph_start = line_start
        paragraph_end = line_end

    flush_paragraph()
    if fence is not None:  # unclosed fence runs to the end of the document
        ranges.append((fence[2], len(text)))
    return ranges


def _inline_code_ranges(text: str, start: int, end: int) -> list[tuple[int, int]]:
    """Inline code spans within one paragraph: a backtick run closes at the
    next run of exactly the same length; an unmatched run is literal."""
    runs = [(m.start() + start, m.end() + start) for m in re.finditer(r"`+", text[start:end])]
    spans: list[tuple[int, int]] = []
    i = 0
    while i < len(runs):
        length = runs[i][1] - runs[i][0]
        close = next((j for j in range(i + 1, len(runs)) if runs[j][1] - runs[j][0] == length), None)
        if close is None:
            i += 1
            continue
        spans.append((runs[i][0], runs[close][1]))
        i = close + 1
    return spans


def _overlaps(ranges: list[tuple[int, int]], start: int, end: int) -> tuple[int, int] | None:
    for r_start, r_end in ranges:
        if r_start < end and start < r_end:
            return r_start, r_end
    return None


def _parse_inner(inner: str) -> tuple[str, str | None, str | None]:
    target_part, has_alias, alias_part = inner.partition("|")
    alias = (alias_part.strip() or None) if has_alias else None
    target_part = target_part.rstrip("\\")  # table rows write the pipe as "\|"
    target, _, heading_part = target_part.partition("#")
    return target.strip(), alias, heading_part.strip() or None


def find_wikilinks(text: str) -> list[WikiLink]:
    code = find_code_ranges(text)
    links: list[WikiLink] = []
    pos = 0
    while True:
        start = text.find("[[", pos)
        if start == -1:
            break
        hit = _overlaps(code, start, start + 2)
        if hit:
            pos = hit[1]
            continue
        close = text.find("]]", start + 2)
        if close == -1:
            break
        inner = text[start + 2 : close]
        nested = inner.find("[[")
        if nested != -1:
            pos = start + 2 + nested
            continue
        if "\n" in inner or not inner.strip() or _overlaps(code, start, close + 2):
            pos = start + 2
            continue
        target, alias, heading = _parse_inner(inner)
        links.append(WikiLink(target, alias, heading, start, close + 2))
        pos = close + 2
    return links


def remove_links_to(text: str, target_keys: set[str]) -> str:
    """Strips every real link whose target (via `title_key`) is in `target_keys`.

    A bare list entry (`- [[X]]: why`) is removed as a whole line; any other
    link becomes its alias, or its target, as plain text. Code is untouched.
    """
    line_removals: list[tuple[int, int]] = []
    inline_edits: list[tuple[int, int, str]] = []
    for link in find_wikilinks(text):
        if not link.target or title_key(link.target) not in target_keys:
            continue
        line_start = text.rfind("\n", 0, link.start) + 1
        if _BULLET_PREFIX.match(text[line_start : link.start]):
            line_end = text.find("\n", link.end)
            line_end = len(text) if line_end == -1 else line_end + 1
            if (line_start, line_end) not in line_removals:
                line_removals.append((line_start, line_end))
        else:
            inline_edits.append((link.start, link.end, link.alias or link.target))

    # An inline edit on a line that is being removed anyway is redundant.
    edits = [(s_, e_, "") for s_, e_ in line_removals] + [
        edit for edit in inline_edits if not any(l_s <= edit[0] < l_e for l_s, l_e in line_removals)
    ]
    result = text
    for start, end, replacement in sorted(edits, reverse=True):
        result = result[:start] + replacement + result[end:]
    return result

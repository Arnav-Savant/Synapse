"""Builds and edits note files deterministically (spec §7.3, §20.3-20.4).

Agents return body sections only; this module assembles the whole file:
frontmatter, `Up:` line, body, then `## Subtopics`, `## Related`,
`## References`. Link-only edits to existing notes are line-level insertions
that leave every other line byte-identical.
"""

import re
from dataclasses import dataclass, field

from app.vault.frontmatter import FrontmatterError, dump_frontmatter, split_frontmatter
from app.vault.titles import title_key
from app.vault.wikilinks import find_code_ranges, find_wikilinks

SECTIONS = ("Subtopics", "Related", "References")  # order they appear in a note
_HEADING = re.compile(r"^## (.+?)\s*$")
_MD_URL = re.compile(r"\]\(([^)\s]+)\)")


@dataclass
class NoteParts:
    title: str
    meta: dict
    body: str
    parents: list[str] = field(default_factory=list)
    children: list[tuple[str, str]] = field(default_factory=list)  # (title, one-line pointer)
    related: list[tuple[str, str]] = field(default_factory=list)  # (title, why)
    references: list[tuple[str, str]] = field(default_factory=list)  # (markdown link or URL, annotation)


def _wikilink_line(title: str, note: str) -> str:
    return f"- [[{title}]]" + (f": {note}" if note else "")


def _reference_line(link: str, note: str) -> str:
    return f"- {link}" + (f": {note}" if note else "")


def _reference_url(link: str) -> str:
    match = _MD_URL.search(link)
    return (match.group(1) if match else link).strip().strip("<>").rstrip("/").lower()


def _escape_fence_lines(body: str) -> str:
    """A body line that is only `---` would read as a frontmatter fence; escape it
    (outside code, where it must stay literal)."""
    code = find_code_ranges(body)
    out: list[str] = []
    offset = 0
    for line in body.splitlines(keepends=True):
        in_code = any(s <= offset < e for s, e in code)
        if not in_code and line.rstrip("\r\n").strip() == "---":
            line = line.replace("---", r"\---", 1)
        out.append(line)
        offset += len(line)
    return "".join(out)


def assemble_note(parts: NoteParts) -> str:
    meta = dict(parts.meta)
    meta["parents"] = [f"[[{p}]]" for p in parts.parents]
    meta.pop("type", None)  # the graph is dense, not typed (spec §7.2)

    chunks = [dump_frontmatter(meta).rstrip("\n")]
    if parts.parents:
        chunks.append("Up: " + ", ".join(f"[[{p}]]" for p in parts.parents))
    body = _escape_fence_lines(parts.body.strip())
    if body:
        chunks.append(body)
    if parts.children:
        chunks.append("## Subtopics\n" + "\n".join(_wikilink_line(t, n) for t, n in parts.children))
    if parts.related:
        chunks.append("## Related\n" + "\n".join(_wikilink_line(t, n) for t, n in parts.related))
    if parts.references:
        chunks.append("## References\n" + "\n".join(_reference_line(l, n) for l, n in parts.references))
    return "\n\n".join(chunks) + "\n"


def _section_bounds(lines: list[str], section: str) -> tuple[int, int] | None:
    """(heading line index, index of the next `## ` heading or len(lines)),
    ignoring headings inside code fences."""
    text = "".join(lines)
    code = find_code_ranges(text)
    heading_at: list[tuple[int, str]] = []
    offset = 0
    for i, line in enumerate(lines):
        m = _HEADING.match(line.rstrip("\r\n"))
        if m and not any(s <= offset < e for s, e in code):
            heading_at.append((i, m.group(1)))
        offset += len(line)
    for n, (i, name) in enumerate(heading_at):
        if name == section:
            end = heading_at[n + 1][0] if n + 1 < len(heading_at) else len(lines)
            return i, end
    return None


def _section_has(lines: list[str], bounds: tuple[int, int], section: str, entry: tuple[str, str]) -> bool:
    body = "".join(lines[bounds[0] + 1 : bounds[1]])
    if section == "References":
        urls = _MD_URL.findall(body) + re.findall(r"https?://[^\s<>)\]]+", body)
        return _reference_url(entry[0]) in {_reference_url(u) for u in urls}
    return title_key(entry[0]) in {title_key(link.target) for link in find_wikilinks(body)}


def insert_link_line(existing_text: str, section: str, entry: tuple[str, str]) -> str:
    """Adds one list entry to `## {section}` (creating the section in its
    proper place if missing). Every other line stays byte-identical. A no-op
    if the entry's link target / URL is already in that section."""
    if section not in SECTIONS:
        raise ValueError(f"unknown section {section!r}; expected one of {SECTIONS}")
    nl = "\r\n" if "\r\n" in existing_text else "\n"
    lines = existing_text.splitlines(keepends=True)
    new_line = (_reference_line(*entry) if section == "References" else _wikilink_line(*entry)) + nl

    bounds = _section_bounds(lines, section)
    if bounds is not None:
        if _section_has(lines, bounds, section, entry):
            return existing_text
        insert_at = bounds[1]
        while insert_at > bounds[0] + 1 and lines[insert_at - 1].strip() == "":
            insert_at -= 1
        if insert_at > 0 and not lines[insert_at - 1].endswith(("\n", "\r")):
            lines[insert_at - 1] += nl
        lines.insert(insert_at, new_line)
        return "".join(lines)

    # Section is missing: place it before the first later section, else at the end.
    later = SECTIONS[SECTIONS.index(section) + 1 :]
    anchor = next((b[0] for name in later if (b := _section_bounds(lines, name))), None)
    block = [f"## {section}{nl}", new_line]
    if anchor is None:
        if lines and not lines[-1].endswith(("\n", "\r")):
            lines[-1] += nl
        if lines and lines[-1].strip() != "":
            lines.append(nl)
        return "".join(lines + block)
    return "".join(lines[:anchor] + block + [nl] + lines[anchor:])


def merge_additive(
    existing_text: str, new_related: list[tuple[str, str]], new_refs: list[tuple[str, str]]
) -> str:
    """Appends only the related links / references that are absent; every
    existing line, including ones the owner added, is preserved."""
    text = existing_text
    for entry in new_related:
        text = insert_link_line(text, "Related", entry)
    for entry in new_refs:
        text = insert_link_line(text, "References", entry)
    return text


def section_span(text: str, section: str) -> tuple[int, int] | None:
    """Character offsets of a `## {section}` block (heading included), or None."""
    lines = text.splitlines(keepends=True)
    bounds = _section_bounds(lines, section)
    if bounds is None:
        return None
    start = sum(len(l) for l in lines[: bounds[0]])
    return start, sum(len(l) for l in lines[: bounds[1]])


def _set_up_line(body: str, parents: list[str]) -> str:
    nl = "\r\n" if "\r\n" in body else "\n"
    lines = body.splitlines(keepends=True)
    up_index = next((i for i, l in enumerate(lines[:10]) if l.lstrip().startswith("Up:")), None)
    new_line = "Up: " + ", ".join(f"[[{p}]]" for p in parents) + nl

    if parents:
        if up_index is not None:
            lines[up_index] = new_line
        else:
            first = next((i for i, l in enumerate(lines) if l.strip()), len(lines))
            lines[first:first] = [new_line, nl]
    elif up_index is not None:
        del lines[up_index]
        blank_before = up_index == 0 or lines[up_index - 1].strip() == ""
        if blank_before and up_index < len(lines) and lines[up_index].strip() == "":
            del lines[up_index]
    return "".join(lines)


def set_parents(text: str, parent_titles: list[str]) -> str:
    """Rewrites the `parents` frontmatter key and the `Up:` line (removed when
    there are no parents). The rest of the body is untouched. A note whose
    frontmatter is unreadable is returned unchanged."""
    try:
        meta, body = split_frontmatter(text)
    except FrontmatterError:
        return text
    head = text[: len(text) - len(body)]
    if meta:
        meta["parents"] = [f"[[{p}]]" for p in parent_titles]
        head = dump_frontmatter(meta)
    return head + _set_up_line(body, parent_titles)


def drop_empty_sections(text: str) -> str:
    """Removes `## Subtopics/Related/References` blocks that have a heading but no content."""
    for section in SECTIONS:
        lines = text.splitlines(keepends=True)
        bounds = _section_bounds(lines, section)
        if bounds is None or any(l.strip() for l in lines[bounds[0] + 1 : bounds[1]]):
            continue
        kept = lines[: bounds[0]] + lines[bounds[1] :]
        if bounds[1] >= len(lines):  # it was the last block: don't leave a trailing blank gap
            while kept and kept[-1].strip() == "":
                kept.pop()
            if kept and not kept[-1].endswith(("\n", "\r")):
                kept[-1] += "\n"
            elif kept:
                kept.append("")  # keep one final newline
        text = "".join(kept)
    return text


_WIKI_ENTRY = re.compile(r"^- \[\[(.+?)\]\](?:: (.*))?$")
_REF_ENTRY = re.compile(r"^- (\[[^\]]*\]\([^)]*\)|\S+)(?:: (.*))?$")


def replace_body(existing_text: str, new_body: str) -> str:
    """Swaps a note's body for `new_body`, keeping its frontmatter, `Up:` line and the
    Subtopics/Related/References blocks exactly as they are."""
    _, body = split_frontmatter(existing_text)
    head = existing_text[: len(existing_text) - len(body)]
    lines = body.splitlines(keepends=True)
    up_index = next((i for i, l in enumerate(lines[:10]) if l.lstrip().startswith("Up:")), None)
    up_block = "".join(lines[: up_index + 1]).strip("\n") + "\n\n" if up_index is not None else ""
    starts = [b[0] for name in SECTIONS if (b := _section_bounds(lines, name))]
    tail = "".join(lines[min(starts) :]).strip("\n") + "\n" if starts else ""
    return head + "\n" + up_block + new_body.strip() + "\n" + ("\n" + tail if tail else "")


def section_lines(text: str, section: str) -> list[str]:
    lines = text.splitlines()
    bounds = _section_bounds(lines, section)
    return [l for l in lines[bounds[0] + 1 : bounds[1]] if l.strip()] if bounds else []


def carry_over_sections(prior_text: str, new_text: str) -> str:
    """When a draft is regenerated, keeps the Related and References entries the earlier
    version had (they are not the writer's output, so regenerating must not lose them)."""
    for section, pattern in (("Related", _WIKI_ENTRY), ("References", _REF_ENTRY)):
        have = set(section_lines(new_text, section))
        for line in section_lines(prior_text, section):
            match = pattern.match(line)
            if match and line not in have:
                new_text = insert_link_line(new_text, section, (match.group(1), match.group(2) or ""))
    return new_text


def strip_link_sections(text: str) -> str:
    """The note without its Subtopics/Related/References blocks: the prose a reviewer should judge.
    Those blocks are generated and checked by code, not written by the model."""
    for section in SECTIONS:
        lines = text.splitlines(keepends=True)
        bounds = _section_bounds(lines, section)
        if bounds is not None:
            text = "".join(lines[: bounds[0]] + lines[bounds[1] :])
    return text

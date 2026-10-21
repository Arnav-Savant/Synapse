"""Deterministic checks on an assembled draft, run before the Validator agent (spec §8 step 10).

Cheap and exact, so the LLM validator only judges what rules cannot: scope,
depth and accuracy.
"""

import re

from app.schemas.validation import Issue
from app.vault.frontmatter import FrontmatterError, split_frontmatter
from app.vault.titles import InvalidTitleError, sanitize_title, title_key
from app.vault.wikilinks import find_code_ranges, find_wikilinks

REQUIRED_KEYS = ("synapse_id", "domain", "parents", "aliases", "summary", "job_id", "created")
_H2 = re.compile(r"^## (.+?)\s*$")


def check_draft_rules(
    *, title: str, text: str, vault_titles: set[str], sibling_titles: set[str], max_chars: int = 60_000
) -> list[Issue]:
    issues: list[Issue] = []

    try:
        if sanitize_title(title) != title:
            issues.append(Issue(code="bad_title", message=f"title {title!r} contains characters that are not allowed in note names"))
    except InvalidTitleError:
        issues.append(Issue(code="bad_title", message="the title is empty"))

    if len(text) > max_chars:
        issues.append(Issue(code="too_large", message=f"the note is {len(text)} characters; the limit is {max_chars}"))

    try:
        meta, body = split_frontmatter(text)
    except FrontmatterError as exc:
        return issues + [Issue(code="frontmatter_invalid", message=str(exc))]
    if not meta:
        return issues + [Issue(code="frontmatter_invalid", message="the note has no frontmatter block")]
    missing = [k for k in REQUIRED_KEYS if k not in meta]
    if missing:
        issues.append(Issue(code="frontmatter_missing_keys", message=f"frontmatter is missing {missing}"))
    if "type" in meta:
        issues.append(Issue(code="frontmatter_forbidden_key", message="frontmatter must not have a `type` key"))

    if not body.strip():
        issues.append(Issue(code="empty_body", message="the note has no body"))

    code = find_code_ranges(body)
    resolvable = {title_key(t) for t in vault_titles | sibling_titles | {title}}
    unresolved: list[str] = []
    for link in find_wikilinks(body):
        if not link.target:
            continue
        if ".." in link.target or "/" in link.target or "\\" in link.target:
            issues.append(Issue(code="unsafe_link", message=f"link [[{link.target}]] contains a path; links must be plain note titles"))
        elif title_key(link.target) not in resolvable and link.target not in unresolved:
            unresolved.append(link.target)
    if unresolved:
        issues.append(Issue(code="dangling_link", message=f"links to notes that do not exist: {unresolved}"))

    offset = 0
    lines = body.splitlines(keepends=True)
    headings: list[tuple[int, str]] = []
    for i, line in enumerate(lines):
        in_code = any(s <= offset < e for s, e in code)
        if not in_code:
            if line.rstrip("\r\n").strip() == "---":
                issues.append(Issue(code="fence_in_body", message="the body has a bare `---` line that would read as a frontmatter fence"))
            m = _H2.match(line.rstrip("\r\n"))
            if m:
                headings.append((i, m.group(1)))
        offset += len(line)
    for n, (i, name) in enumerate(headings):
        end = headings[n + 1][0] if n + 1 < len(headings) else len(lines)
        if not "".join(lines[i + 1 : end]).strip():
            issues.append(Issue(code="empty_section", message=f"section '{name}' is empty"))
    return issues

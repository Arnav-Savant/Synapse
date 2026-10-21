"""YAML frontmatter for notes: split from / dump to markdown text."""

import yaml

# Key order from the spec (§7.2). `topic_id` is written only when set (twins).
# Any other keys (for example ones the owner added in Obsidian) follow, in
# their original order, so Synapse never drops them.
_KEY_ORDER = ("synapse_id", "topic_id", "domain", "parents", "aliases", "summary", "job_id", "created")
_FENCE = "---"


class FrontmatterError(ValueError):
    """A note's frontmatter block is present but is not valid YAML."""


def split_frontmatter(text: str) -> tuple[dict, str]:
    """Returns (metadata, body). No frontmatter block -> ({}, text) unchanged.
    The body is everything after the closing fence line."""
    lines = text.splitlines(keepends=True)
    if not lines or lines[0].rstrip("\r\n") != _FENCE:
        return {}, text
    for i in range(1, len(lines)):
        if lines[i].rstrip("\r\n") == _FENCE:
            raw = "".join(lines[1:i])
            try:
                meta = yaml.safe_load(raw) if raw.strip() else {}
            except yaml.YAMLError as exc:
                raise FrontmatterError(f"frontmatter is not valid YAML: {exc}") from exc
            if not isinstance(meta, dict):
                raise FrontmatterError("frontmatter must be a YAML mapping")
            return meta, "".join(lines[i + 1 :])
    return {}, text  # opening fence without a closing one: treat the file as plain markdown


def dump_frontmatter(meta: dict) -> str:
    """Returns the frontmatter block including both fences and a trailing newline."""
    ordered = {k: meta[k] for k in _KEY_ORDER if meta.get(k) is not None}
    ordered.update({k: v for k, v in meta.items() if k not in _KEY_ORDER and v is not None})
    body = yaml.safe_dump(ordered, default_flow_style=None, allow_unicode=True, sort_keys=False, width=10_000)
    return f"{_FENCE}\n{body}{_FENCE}\n"

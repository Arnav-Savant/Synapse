"""YAML frontmatter for notes: split from / dump to markdown text."""

import yaml

# Key order of a note's frontmatter. `topic_id` is written only when set (cross-domain copies) and `hub` only on hubs.
# Any other keys (for example ones the owner added in Obsidian) follow, in
# their original order, so Synapse never drops them.
_KEY_ORDER = ("synapse_id", "topic_id", "domain", "hub", "parents", "aliases", "summary", "job_id", "created")
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
                raise FrontmatterError(f"frontmatter is not valid YAML: {str(exc).splitlines()[0]}") from exc
            if not isinstance(meta, dict):
                raise FrontmatterError("frontmatter must be a YAML mapping")
            return meta, "".join(lines[i + 1 :])
    return {}, text  # opening fence without a closing one: treat the file as plain markdown


def dump_frontmatter(meta: dict) -> str:
    """Returns the frontmatter block including both fences and a trailing newline."""
    ordered = {k: meta[k] for k in _KEY_ORDER if meta.get(k) is not None}
    ordered.update({k: v for k, v in meta.items() if k not in _KEY_ORDER and v is not None})
    # One key at a time: scalars stay one-per-line (block style) while lists
    # stay compact (`aliases: [a, b]`), which is how Obsidian shows properties.
    body = "".join(
        yaml.safe_dump(
            {k: v},
            default_flow_style=None if isinstance(v, (list, tuple)) else False,
            allow_unicode=True,
            sort_keys=False,
            width=10_000,
        )
        for k, v in ordered.items()
    )
    return f"{_FENCE}\n{body}{_FENCE}\n"


def with_meta(text: str, updates: dict) -> str:
    """Returns `text` with `updates` merged into its frontmatter (a block is
    created if there is none). The body after the frontmatter is untouched."""
    meta, body = split_frontmatter(text)
    meta.update(updates)
    return dump_frontmatter(meta) + body

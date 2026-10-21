"""What a Writer/Synthesizer returns: body sections only (spec §20.3).

Deterministic code adds frontmatter, `Up:`, `## Subtopics`, `## Related` and
`## References`, so an agent can never produce a malformed or hostile file.
"""

import re

from pydantic import BaseModel, Field

# Headings that belong to the assembled note, never to an agent's body.
RESERVED_HEADINGS = ("up", "subtopics", "related", "references")
_RESERVED_LINE = re.compile(r"^ {0,3}#{1,6}\s*(up|subtopics|related|references)\s*:?\s*$", re.IGNORECASE | re.MULTILINE)


class NoteBody(BaseModel):
    intro: str = Field(default="", description="optional lead text before the first section")
    sections: dict[str, str] = Field(description="section heading -> markdown body of that section")
    summary: str = Field(description="one line saying what the note is about")
    aliases: list[str] = Field(default_factory=list, description="other names the topic goes by")

    def render(self) -> str:
        """The body as markdown: intro, then each section under a `##` heading."""
        parts = [self.intro.strip()] if self.intro.strip() else []
        parts += [f"## {heading}\n\n{text.strip()}" for heading, text in self.sections.items() if text.strip()]
        return "\n\n".join(parts)


def clean_body(body: NoteBody) -> tuple[NoteBody, bool]:
    """Drops reserved sections and reserved heading lines. Returns (body, whether anything was removed)."""
    changed = False
    sections: dict[str, str] = {}
    for heading, text in body.sections.items():
        if heading.strip().lower() in RESERVED_HEADINGS:
            changed = True
            continue
        cleaned = _RESERVED_LINE.sub("", text)
        changed |= cleaned != text
        sections[heading.strip()] = cleaned
    intro = _RESERVED_LINE.sub("", body.intro)
    changed |= intro != body.intro
    return body.model_copy(update={"sections": sections, "intro": intro}), changed

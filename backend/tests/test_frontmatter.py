import pytest

from app.knowledge import frontmatter


def test_parse_valid_concept():
    raw = """---
id: prompt-injection
title: Prompt Injection
aliases: ["Prompt Injection Attack"]
domains: [prompt-engineering, ai-security]
status: developing
created: 2026-09-22
updated: 2026-09-22
sources: [prompt-engineering/chat-001.md]
relationships:
  - type: subtopic-of
    target: prompt-engineering
  - type: example-of
    target: few-shot-prompting
    note: some note
---

# Prompt Injection

Body text with a [[wikilink]].
"""

    concept = frontmatter.parse(raw)

    assert concept.id == "prompt-injection"
    assert concept.title == "Prompt Injection"
    assert concept.aliases == ["Prompt Injection Attack"]
    assert concept.domains == ["prompt-engineering", "ai-security"]
    assert concept.status == "developing"
    assert concept.created == "2026-09-22"
    assert concept.sources == ["prompt-engineering/chat-001.md"]
    assert len(concept.relationships) == 2
    assert concept.relationships[0].type == "subtopic-of"
    assert concept.relationships[0].target == "prompt-engineering"
    assert concept.relationships[0].note is None
    assert concept.relationships[1].note == "some note"
    assert "Body text with a [[wikilink]]." in concept.body
    assert "---" not in concept.body


def test_parse_minimal_concept_defaults():
    raw = """---
id: stub-concept
title: Stub Concept
---
body
"""

    concept = frontmatter.parse(raw)

    assert concept.status == "stub"
    assert concept.aliases == []
    assert concept.domains == []
    assert concept.relationships == []
    assert concept.sources == []


def test_parse_rejects_missing_frontmatter():
    with pytest.raises(frontmatter.FrontmatterError):
        frontmatter.parse("# just a heading\nno frontmatter here")


def test_parse_rejects_unclosed_frontmatter():
    with pytest.raises(frontmatter.FrontmatterError):
        frontmatter.parse("---\nid: x\ntitle: X\nno closing delimiter")


def test_parse_rejects_missing_required_fields():
    with pytest.raises(frontmatter.FrontmatterError):
        frontmatter.parse("---\ndomains: [x]\n---\nbody")


def test_parse_rejects_invalid_yaml():
    with pytest.raises(frontmatter.FrontmatterError):
        frontmatter.parse("---\nid: [unclosed\n---\nbody")

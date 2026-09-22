from app.knowledge.wikilinks import extract_links


def test_extract_links_basic():
    body = "See [[prompt-engineering]] and [[few-shot-prompting]]."
    assert extract_links(body) == ["prompt-engineering", "few-shot-prompting"]


def test_extract_links_deduplicates_and_preserves_order():
    body = "[[a]] then [[b]] then [[a]] again"
    assert extract_links(body) == ["a", "b"]


def test_extract_links_strips_display_text():
    body = "See [[few-shot-prompting|the few-shot technique]]."
    assert extract_links(body) == ["few-shot-prompting"]


def test_extract_links_ignores_single_brackets():
    body = "A [regular link](http://example.com) and [not-a-wikilink]."
    assert extract_links(body) == []


def test_extract_links_empty_body():
    assert extract_links("") == []

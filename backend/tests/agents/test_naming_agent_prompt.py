import pytest

from app.agents.naming_agent import NamingAgentError, build_prompt, parse_category


def test_build_prompt_includes_existing_categories_and_content():
    prompt = build_prompt(["rag", "prompt-engineering"], "some raw pasted content", None)

    assert "rag" in prompt
    assert "prompt-engineering" in prompt
    assert "some raw pasted content" in prompt


def test_build_prompt_with_no_existing_categories_says_so():
    prompt = build_prompt([], "content", None)

    assert "none yet" in prompt.lower()


def test_build_prompt_without_topic_hint_says_none_was_given():
    prompt = build_prompt(["rag"], "content", None)

    assert "No topic hint was given" in prompt


def test_build_prompt_with_topic_hint_includes_it():
    prompt = build_prompt(["rag"], "content", "retrieval augmented generation")

    assert "retrieval augmented generation" in prompt


def test_build_prompt_instructs_json_only_output_contract():
    prompt = build_prompt(["rag"], "content", None)

    assert "JSON" in prompt
    assert '"category"' in prompt


def test_parse_category_on_clean_valid_json():
    assert parse_category('{"category": "rag"}') == "rag"


def test_parse_category_on_prose_wrapped_response():
    text = 'Sure, here you go:\n```json\n{"category": "rag"}\n```'

    assert parse_category(text) == "rag"


def test_parse_category_strips_whitespace():
    assert parse_category('{"category": "  rag  "}') == "rag"


def test_parse_category_raises_on_no_json_at_all():
    with pytest.raises(NamingAgentError):
        parse_category("I think this belongs under rag, no JSON here though.")


def test_parse_category_raises_on_json_missing_required_key():
    with pytest.raises(NamingAgentError):
        parse_category('{"filename": "hybrid-search"}')


def test_parse_category_raises_on_empty_category():
    with pytest.raises(NamingAgentError):
        parse_category('{"category": ""}')

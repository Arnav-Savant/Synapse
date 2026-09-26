import json

import pytest

from app.agents.validation_agent import (
    GRAPH_AGENT_CATEGORIES,
    TEXT_AGENT_CATEGORIES,
    ValidationAgentOutput,
    ValidationAgentOutputParseError,
    build_prompt,
    parse_output,
    target_agent_for_category,
)


def _text_agent_result() -> dict:
    return {
        "segmentation": [{"title": "Backprop", "scope_description": "...", "source_excerpt_ref": "..."}],
        "overlap_check": {"merged_pairs": [], "notes": "no overlap"},
        "concepts_written": [
            {"concept_id": "concept-1", "title": "Backpropagation", "action": "created"},
        ],
    }


def _graph_agent_result() -> dict:
    return {
        "relationships_written": [
            {"source_id": "concept-1", "target_id": "concept-2", "type": "related-to", "action": "created"}
        ]
    }


def test_build_prompt_includes_text_agent_output_and_read_only_reminder():
    prompt = build_prompt(_text_agent_result())

    assert "concept-1" in prompt
    assert "Backpropagation" in prompt
    assert "read-only" in prompt.lower() or "read tools" in prompt.lower()
    assert "no write tools" in prompt.lower()


def test_build_prompt_without_graph_agent_result_notes_graph_agent_did_not_run():
    prompt = build_prompt(_text_agent_result(), graph_agent_result=None)

    assert "Graph Agent did not run this round" in prompt
    assert "concept-2" not in prompt


def test_build_prompt_with_graph_agent_result_includes_relationships_written():
    prompt = build_prompt(_text_agent_result(), graph_agent_result=_graph_agent_result())

    assert "concept-1" in prompt
    assert "concept-2" in prompt
    assert "related-to" in prompt


def test_build_prompt_includes_precision_over_recall_instruction():
    prompt = build_prompt(_text_agent_result())

    assert "precision over recall" in prompt.lower() or "reject on doubt" in prompt.lower()


def test_build_prompt_includes_closed_category_taxonomy():
    prompt = build_prompt(_text_agent_result())

    for category in TEXT_AGENT_CATEGORIES + GRAPH_AGENT_CATEGORIES:
        assert category in prompt


def test_target_agent_for_category_maps_text_agent_categories():
    for category in TEXT_AGENT_CATEGORIES:
        assert target_agent_for_category(category) == "text_agent"


def test_target_agent_for_category_maps_graph_agent_categories():
    for category in GRAPH_AGENT_CATEGORIES:
        assert target_agent_for_category(category) == "graph_agent"


def test_target_agent_for_category_raises_on_unknown_category():
    with pytest.raises(ValueError):
        target_agent_for_category("not_a_real_category")


def test_parse_output_on_clean_valid_json_pass_verdict():
    payload = {"verdict": "pass", "issues": []}
    result_text = json.dumps(payload)

    output = parse_output(result_text)

    assert isinstance(output, ValidationAgentOutput)
    assert output.verdict == "pass"
    assert output.issues == []
    assert output.raw_result_text == result_text


def test_parse_output_on_clean_valid_json_reject_verdict_with_issues():
    payload = {
        "verdict": "reject",
        "issues": [
            {
                "category": "unsupported_justification",
                "severity": "blocking",
                "target_id": "concept-1->concept-2",
                "description": "justification does not establish the claim",
            }
        ],
    }
    result_text = json.dumps(payload)

    output = parse_output(result_text)

    assert output.verdict == "reject"
    assert output.issues == payload["issues"]
    assert output.raw_result_text == result_text


def test_parse_output_on_prose_wrapped_response():
    payload = {"verdict": "pass", "issues": []}
    result_text = (
        "I checked everything and found no issues.\n\n"
        f"{json.dumps(payload)}\n\n"
        "Let me know if you need anything else."
    )

    output = parse_output(result_text)

    assert output.verdict == "pass"
    assert output.raw_result_text == result_text


def test_parse_output_raises_on_no_json_at_all():
    with pytest.raises(ValidationAgentOutputParseError):
        parse_output("I checked everything and found no issues.")


def test_parse_output_raises_on_json_missing_required_key():
    payload = {"issues": []}
    result_text = json.dumps(payload)

    with pytest.raises(ValidationAgentOutputParseError):
        parse_output(result_text)

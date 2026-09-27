import json

import pytest

from app.agents.graph_agent import (
    GraphAgentOutput,
    GraphAgentOutputParseError,
    build_prompt,
    parse_output,
)
from app.repositories.graph_repo import (
    DIRECTIONAL_NOT_HIERARCHICAL_TYPES,
    HIERARCHICAL_TYPES,
    SYMMETRIC_TYPES,
)


def _concepts_written() -> list[dict]:
    return [
        {"concept_id": "concept-1", "title": "Prompt Injection", "action": "created"},
        {"concept_id": "concept-2", "title": "Jailbreaking", "action": "updated"},
    ]


def test_build_prompt_includes_concepts_and_mandatory_first_step():
    prompt = build_prompt(_concepts_written())

    assert "concept-1" in prompt
    assert "Prompt Injection" in prompt
    assert "concept-2" in prompt
    assert "Jailbreaking" in prompt
    assert "Mandatory first step" in prompt
    assert "get_concept_metadata" in prompt
    assert "before anything else" in prompt.lower() or "before doing anything else" in prompt.lower()
    assert "both" in prompt.lower() and "endpoints" in prompt.lower()


def test_build_prompt_includes_tool_boundary_reminder():
    prompt = build_prompt(_concepts_written())

    assert "title" in prompt.lower() and "category" in prompt.lower()
    assert "never" in prompt.lower()
    assert "body content" in prompt.lower()


def test_build_prompt_includes_topological_justification_instruction_and_no_quote_instruction():
    prompt = build_prompt(_concepts_written())

    assert "topological evidence" in prompt.lower()
    assert "never a fabricated text quote" in prompt.lower() or "never a text quote" in prompt.lower()
    assert "quote source" not in prompt.lower()


def test_build_prompt_includes_generated_type_taxonomy():
    prompt = build_prompt(_concepts_written())

    for type_name in HIERARCHICAL_TYPES | SYMMETRIC_TYPES | DIRECTIONAL_NOT_HIERARCHICAL_TYPES:
        assert type_name in prompt


def test_build_prompt_without_critique_delta_omits_delta_section():
    prompt = build_prompt(_concepts_written(), critique_delta=None)

    assert "Additional guidance for this run" not in prompt


def test_build_prompt_with_critique_delta_appends_it_after_base_contract():
    base_prompt = build_prompt(_concepts_written(), critique_delta=None)
    delta = "Pay closer attention to the distinction between X and Y this time."

    prompt = build_prompt(_concepts_written(), critique_delta=delta)

    assert delta in prompt
    assert prompt.startswith(base_prompt)


def test_parse_output_on_clean_valid_json():
    payload = {
        "relationships_written": [
            {"source_id": "concept-1", "target_id": "concept-2", "type": "related-to", "action": "created"}
        ]
    }
    result_text = json.dumps(payload)

    output = parse_output(result_text)

    assert isinstance(output, GraphAgentOutput)
    assert output.relationships_written == payload["relationships_written"]
    assert output.raw_result_text == result_text


def test_parse_output_on_prose_wrapped_response():
    payload = {
        "relationships_written": [
            {"source_id": "concept-2", "target_id": "concept-1", "type": "subtopic-of", "action": "created"}
        ]
    }
    result_text = (
        "I explored the graph and added one relationship:\n\n"
        f"{json.dumps(payload)}\n\n"
        "Let me know if you need anything else."
    )

    output = parse_output(result_text)

    assert output.relationships_written == payload["relationships_written"]
    assert output.raw_result_text == result_text


def test_parse_output_raises_on_no_json_at_all():
    with pytest.raises(GraphAgentOutputParseError):
        parse_output("I explored the graph and found nothing worth relating.")


def test_parse_output_raises_on_json_missing_required_key():
    payload = {"notes": "nothing found"}
    result_text = json.dumps(payload)

    with pytest.raises(GraphAgentOutputParseError):
        parse_output(result_text)


def test_build_prompt_includes_structural_gap_instructions():
    prompt = build_prompt(_concepts_written())

    assert "structural_gaps" in prompt
    assert "search_concepts" in prompt
    assert "missing_parent" in prompt
    assert "get_graph_neighborhood" in prompt


def test_parse_output_defaults_structural_gaps_to_empty_list_when_absent():
    payload = {"relationships_written": []}
    result_text = json.dumps(payload)

    output = parse_output(result_text)

    assert output.structural_gaps == []


def test_parse_output_raises_when_structural_gaps_is_not_a_list():
    payload = {"relationships_written": [], "structural_gaps": {"gap_type": "missing_parent"}}
    result_text = json.dumps(payload)

    with pytest.raises(GraphAgentOutputParseError):
        parse_output(result_text)


def test_parse_output_raises_when_gap_entry_missing_required_key():
    payload = {
        "relationships_written": [],
        "structural_gaps": [
            {
                "gap_type": "missing_parent",
                "member_concept_ids": ["concept-1", "concept-2"],
                "proposed_title": "Neural Networks",
                # proposed_scope_hint and justification both omitted
            }
        ],
    }
    result_text = json.dumps(payload)

    with pytest.raises(GraphAgentOutputParseError):
        parse_output(result_text)


def test_parse_output_raises_when_gap_type_is_not_missing_parent():
    payload = {
        "relationships_written": [],
        "structural_gaps": [
            {
                "gap_type": "missing_child",
                "member_concept_ids": ["concept-1", "concept-2"],
                "proposed_title": "Some Child",
                "proposed_scope_hint": "hint",
                "justification": "justification",
            }
        ],
    }
    result_text = json.dumps(payload)

    with pytest.raises(GraphAgentOutputParseError):
        parse_output(result_text)


def test_parse_output_extracts_structural_gaps_when_present():
    payload = {
        "relationships_written": [],
        "structural_gaps": [
            {
                "gap_type": "missing_parent",
                "member_concept_ids": ["concept-1", "concept-2"],
                "proposed_title": "Neural Networks",
                "proposed_scope_hint": "The umbrella topic covering both members.",
                "justification": "concept-1 and concept-2 share no path to any common ancestor within 2 hops, and search_concepts for 'neural networks' returned no match.",
            }
        ],
    }
    result_text = json.dumps(payload)

    output = parse_output(result_text)

    assert output.structural_gaps == payload["structural_gaps"]

import json

import pytest

from app.agents.text_agent import (
    GapSynthesisOutput,
    GapSynthesisOutputParseError,
    TextAgentOutput,
    TextAgentOutputParseError,
    build_gap_synthesis_prompt,
    build_prompt,
    parse_gap_synthesis_output,
    parse_output,
)
from app.db.models import Source
from app.orchestrator.tools import SourceSignals


def _source(content: str = "Prompt injection lets an attacker override instructions.") -> Source:
    return Source(content=content, topic_hint="prompt injection")


def _signals(**overrides) -> SourceSignals:
    defaults = dict(content_length=57, topic_hint="prompt injection", max_title_similarity=0.42)
    defaults.update(overrides)
    return SourceSignals(**defaults)


def test_build_prompt_includes_content_and_signals_and_stage_instructions():
    source = _source()
    signals = _signals()

    prompt = build_prompt(source, signals)

    assert source.content in prompt
    assert str(signals.content_length) in prompt
    assert signals.topic_hint in prompt
    assert str(signals.max_title_similarity) in prompt
    assert "Stage A" in prompt and "Segmentation" in prompt
    assert "Stage B" in prompt
    assert "overlap" in prompt.lower()
    assert "Stage C" in prompt
    assert "search_concepts" in prompt
    assert "create_concept" in prompt
    assert "update_concept" in prompt


def test_build_prompt_without_critique_delta_omits_delta_section():
    prompt = build_prompt(_source(), _signals(), critique_delta=None)

    assert "Additional guidance for this run" not in prompt


def test_build_prompt_with_critique_delta_appends_it_after_base_contract():
    base_prompt = build_prompt(_source(), _signals(), critique_delta=None)
    delta = "Pay closer attention to the distinction between X and Y this time."

    prompt = build_prompt(_source(), _signals(), critique_delta=delta)

    assert delta in prompt
    assert prompt.startswith(base_prompt)
    assert prompt.index(delta) > prompt.index("Stage C")


def test_parse_output_on_clean_valid_json():
    payload = {
        "segmentation": [
            {
                "title": "Prompt Injection",
                "scope_description": "Definition and mechanics of prompt injection.",
                "source_excerpt_ref": "Prompt injection lets an attacker override instructions.",
            }
        ],
        "overlap_check": {"merged_pairs": [], "notes": "No overlap found."},
        "concepts_written": [
            {"concept_id": "concept-1", "title": "Prompt Injection", "action": "created"}
        ],
    }
    result_text = json.dumps(payload)

    output = parse_output(result_text)

    assert isinstance(output, TextAgentOutput)
    assert output.segmentation == payload["segmentation"]
    assert output.overlap_check == payload["overlap_check"]
    assert output.concepts_written == payload["concepts_written"]
    assert output.raw_result_text == result_text


def test_parse_output_on_prose_wrapped_response():
    payload = {
        "segmentation": [
            {
                "title": "Jailbreaking",
                "scope_description": "How jailbreaking differs from prompt injection.",
                "source_excerpt_ref": "excerpt ref",
            }
        ],
        "overlap_check": {"merged_pairs": [], "notes": ""},
        "concepts_written": [
            {"concept_id": "concept-2", "title": "Jailbreaking", "action": "updated"}
        ],
    }
    result_text = (
        "Here's what I did:\n\n"
        f"{json.dumps(payload)}\n\n"
        "Let me know if you need anything else."
    )

    output = parse_output(result_text)

    assert output.segmentation == payload["segmentation"]
    assert output.overlap_check == payload["overlap_check"]
    assert output.concepts_written == payload["concepts_written"]
    assert output.raw_result_text == result_text


def test_parse_output_raises_on_no_json_at_all():
    with pytest.raises(TextAgentOutputParseError):
        parse_output("I read the source and created two concepts, all done!")


def test_parse_output_raises_on_json_missing_required_key():
    payload = {"segmentation": [], "overlap_check": {"merged_pairs": [], "notes": ""}}
    result_text = json.dumps(payload)

    with pytest.raises(TextAgentOutputParseError):
        parse_output(result_text)


def test_build_gap_synthesis_prompt_create_mode_includes_members_and_proposal():
    prompt = build_gap_synthesis_prompt(
        member_concept_ids=["concept-1", "concept-2"],
        proposed_title="Neural Networks",
        proposed_scope_hint="The umbrella topic covering both members.",
        justification="concept-1 and concept-2 share no common ancestor.",
    )

    assert "concept-1" in prompt
    assert "concept-2" in prompt
    assert "Neural Networks" in prompt
    assert "get_concept" in prompt
    assert "create_concept" in prompt
    assert "origin" in prompt and "gap_synthesis" in prompt
    assert "gap_member_ids" in prompt


def test_build_gap_synthesis_prompt_rework_mode_includes_target_and_metadata_preservation():
    prompt = build_gap_synthesis_prompt(
        rework_target_concept_id="concept-9",
        critique_delta="Validation Agent rejected: the body invents a fact not supported by the members.",
    )

    assert "concept-9" in prompt
    assert "update_concept" in prompt
    assert "Validation Agent rejected" in prompt
    # The non-obvious correctness rule from the spec: metadata is fully
    # replaced by update_concept, so the rework prompt must instruct
    # reading it back and passing it through unchanged.
    assert "get_concept" in prompt
    assert "metadata" in prompt.lower()
    assert "unchanged" in prompt.lower() or "preserve" in prompt.lower()


def test_build_gap_synthesis_prompt_requires_one_complete_mode():
    with pytest.raises(ValueError):
        build_gap_synthesis_prompt()


def test_parse_gap_synthesis_output_on_clean_json():
    payload = {"concept_written": {"concept_id": "concept-9", "title": "Neural Networks", "action": "created"}}
    result_text = json.dumps(payload)

    output = parse_gap_synthesis_output(result_text)

    assert isinstance(output, GapSynthesisOutput)
    assert output.concept_written == payload["concept_written"]


def test_parse_gap_synthesis_output_raises_on_missing_key():
    with pytest.raises(GapSynthesisOutputParseError):
        parse_gap_synthesis_output(json.dumps({"notes": "n/a"}))


def test_parse_gap_synthesis_output_raises_when_concept_written_is_not_an_object():
    payload = {"concept_written": "concept-9"}

    with pytest.raises(GapSynthesisOutputParseError):
        parse_gap_synthesis_output(json.dumps(payload))


def test_parse_gap_synthesis_output_raises_when_concept_written_missing_required_key():
    payload = {"concept_written": {"concept_id": "concept-9", "title": "Neural Networks"}}  # missing "action"

    with pytest.raises(GapSynthesisOutputParseError):
        parse_gap_synthesis_output(json.dumps(payload))


def test_build_gap_synthesis_prompt_rework_mode_requires_both_target_and_critique():
    # Missing critique_delta should raise ValueError
    with pytest.raises(ValueError):
        build_gap_synthesis_prompt(rework_target_concept_id="concept-9")

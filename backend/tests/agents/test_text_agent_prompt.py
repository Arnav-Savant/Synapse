import json

import pytest

from app.agents.text_agent import (
    TextAgentOutput,
    TextAgentOutputParseError,
    build_prompt,
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

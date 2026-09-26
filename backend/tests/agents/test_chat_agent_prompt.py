from app.agents.chat_agent import build_prompt


def test_build_prompt_includes_message_and_read_only_tool_names():
    prompt = build_prompt("What is prompt injection?", None)

    assert "What is prompt injection?" in prompt
    assert "search_concepts" in prompt
    assert "get_concept" in prompt
    assert "get_graph_neighborhood" in prompt


def test_build_prompt_without_concept_id_says_none_is_open():
    prompt = build_prompt("hello", None)

    assert "isn't currently viewing any particular concept" in prompt


def test_build_prompt_with_concept_id_includes_it_as_context_to_consider():
    prompt = build_prompt("tell me more", "prompt-injection")

    assert "prompt-injection" in prompt
    assert "get_concept" in prompt


def test_build_prompt_instructs_no_json_output_contract():
    prompt = build_prompt("hello", None)

    assert "JSON" in prompt

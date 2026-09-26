"""Shared tolerant-JSON-extraction logic for agent structured outputs.

Multiple agents (Text, Graph, and — pending — Validation) end their final
response with a fenced/embedded JSON object reporting what they did, and
each needs to extract it tolerant of prose wrapping (Claude Code is
observed to sometimes wrap JSON in explanatory text despite instruction
not to). This module holds that extraction once, parameterized by the
required keys and the caller's own exception type, rather than duplicating
it per agent.
"""

import json


def extract_json_object(
    result_text: str, required_keys: tuple[str, ...], error_cls: type[Exception]
) -> dict:
    """Extracts the fenced/embedded JSON object from result_text, tolerant of
    prose wrapping: finds the first '{' and the last '}' and attempts
    json.loads on that span, falling back to trimming from the end
    (searching backwards for an earlier '}') when the naive last-'}' span
    doesn't parse. Raises error_cls — never returns a silently-empty result
    — if no valid JSON object with all of required_keys is found.
    """
    start = result_text.find("{")
    if start == -1:
        raise error_cls(f"no JSON object found in response: {result_text!r}")

    end = result_text.rfind("}")
    data = None
    while end > start:
        candidate = result_text[start : end + 1]
        try:
            data = json.loads(candidate)
            break
        except json.JSONDecodeError:
            end = result_text.rfind("}", start, end)

    if data is None:
        raise error_cls(f"no parseable JSON object found in response: {result_text!r}")

    if not isinstance(data, dict):
        raise error_cls(f"parsed JSON is not an object: {result_text!r}")

    missing = [key for key in required_keys if key not in data]
    if missing:
        raise error_cls(f"parsed JSON is missing required keys {missing}: {result_text!r}")

    return data

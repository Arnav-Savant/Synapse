import json

import pytest

from app.agents.structured_output import extract_json_object


class _FakeParseError(Exception):
    """Throwaway exception used to prove extract_json_object is generic
    over the caller's own error type."""


def test_extract_json_object_on_clean_json_with_all_required_keys():
    payload = {"foo": "bar", "baz": [1, 2, 3]}
    result_text = json.dumps(payload)

    data = extract_json_object(result_text, ("foo", "baz"), _FakeParseError)

    assert data == payload


def test_extract_json_object_on_prose_wrapped_json():
    payload = {"foo": "bar"}
    result_text = (
        "Here's what I did:\n\n"
        f"{json.dumps(payload)}\n\n"
        "Let me know if you need anything else."
    )

    data = extract_json_object(result_text, ("foo",), _FakeParseError)

    assert data == payload


def test_extract_json_object_raises_given_error_cls_on_missing_required_key():
    payload = {"foo": "bar"}
    result_text = json.dumps(payload)

    with pytest.raises(_FakeParseError):
        extract_json_object(result_text, ("foo", "missing_key"), _FakeParseError)


def test_extract_json_object_raises_given_error_cls_on_no_json_at_all():
    with pytest.raises(_FakeParseError):
        extract_json_object("no braces here at all", ("foo",), _FakeParseError)


def test_extract_json_object_raises_given_error_cls_on_unparseable_garbage():
    result_text = "{not: valid, json at all}"

    with pytest.raises(_FakeParseError):
        extract_json_object(result_text, ("foo",), _FakeParseError)

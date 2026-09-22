import pytest

from app.repositories.paths import PathTraversalError, resolve_within


def test_resolve_within_allows_nested_valid_path(tmp_path):
    result = resolve_within(tmp_path, "category", "file.md")

    assert result == (tmp_path / "category" / "file.md").resolve()


def test_resolve_within_rejects_dotdot_segment(tmp_path):
    with pytest.raises(PathTraversalError):
        resolve_within(tmp_path, "..", "etc", "passwd")


def test_resolve_within_rejects_dotdot_inside_a_single_segment(tmp_path):
    with pytest.raises(PathTraversalError):
        resolve_within(tmp_path, "../../etc", "passwd")


def test_resolve_within_rejects_empty_segment(tmp_path):
    with pytest.raises(PathTraversalError):
        resolve_within(tmp_path, "")

import subprocess

import pytest

from app.claude_runner import git_guard


def _last_commit_message(repo_path) -> str:
    result = subprocess.run(
        ["git", "log", "-1", "--pretty=%s"], cwd=repo_path, capture_output=True, text=True, check=True
    )
    return result.stdout.strip()


def test_ensure_clean_passes_on_clean_repo(tmp_path, git_repo_factory):
    git_repo_factory(tmp_path)
    git_guard.ensure_clean(tmp_path)


def test_ensure_clean_raises_on_dirty_repo(tmp_path, git_repo_factory):
    git_repo_factory(tmp_path)
    (tmp_path / "knowledge" / "new.md").write_text("dirty")

    with pytest.raises(git_guard.DirtyWorkingTreeError):
        git_guard.ensure_clean(tmp_path)


def test_finalize_commits_knowledge_changes(tmp_path, git_repo_factory):
    git_repo_factory(tmp_path)
    (tmp_path / "knowledge" / "concept.md").write_text("# Concept")

    committed = git_guard.finalize(tmp_path, "test commit")

    assert committed == ["knowledge/concept.md"]
    assert _last_commit_message(tmp_path) == "test commit"


def test_finalize_reverts_source_changes_and_raises(tmp_path, git_repo_factory):
    git_repo_factory(tmp_path)
    (tmp_path / "source" / "evil.md").write_text("should not survive")

    with pytest.raises(git_guard.SourceModifiedError) as exc_info:
        git_guard.finalize(tmp_path, "test commit")

    assert "source/evil.md" in exc_info.value.changed_paths
    assert not (tmp_path / "source" / "evil.md").exists()


def test_finalize_reverts_source_when_content_dir_is_a_subdirectory_of_a_larger_repo(
    tmp_path, git_repo_factory
):
    """The real shape now (docs/ARCHITECTURE.md §1): synapse-knowledge/ is a
    subdirectory of the app repo, not a repo root of its own. `git status
    --porcelain` reports paths relative to the repo root in that case, not
    to `-C repo_path` — if git_guard didn't correct for that, the
    `source/`-prefix check silently stops matching and the safety net goes
    dark."""
    repo_root = tmp_path / "Synapse"
    content_dir = repo_root / "synapse-knowledge"
    git_repo_factory(repo_root, with_content_dirs=False)
    (content_dir / "source").mkdir(parents=True)
    (content_dir / "knowledge").mkdir()
    (content_dir / "source" / ".gitkeep").touch()
    (content_dir / "knowledge" / ".gitkeep").touch()
    subprocess.run(["git", "add", "-A"], cwd=repo_root, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "content dirs"], cwd=repo_root, check=True)

    (content_dir / "knowledge" / "concept.md").write_text("# Concept")
    (content_dir / "source" / "evil.md").write_text("should not survive")

    with pytest.raises(git_guard.SourceModifiedError) as exc_info:
        git_guard.finalize(content_dir, "test commit")

    assert exc_info.value.changed_paths == ["source/evil.md"]
    assert not (content_dir / "source" / "evil.md").exists()
    assert _last_commit_message(repo_root) == "test commit"


def test_finalize_commits_knowledge_and_reverts_source_in_same_run(tmp_path, git_repo_factory):
    """The adversarial case: a run that legitimately updates knowledge/ but
    also (maliciously or buggily) touches source/ in the same run must
    still commit the legitimate part and revert the bad part."""
    git_repo_factory(tmp_path)
    (tmp_path / "knowledge" / "concept.md").write_text("# Concept")
    (tmp_path / "source" / "evil.md").write_text("should not survive")

    with pytest.raises(git_guard.SourceModifiedError):
        git_guard.finalize(tmp_path, "test commit")

    assert not (tmp_path / "source" / "evil.md").exists()
    assert _last_commit_message(tmp_path) == "test commit"

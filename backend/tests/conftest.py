"""Shared pytest fixtures."""

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def git_repo_factory():
    """Returns a callable that git-inits a directory (with a usable local
    user config, and the standard source/knowledge dirs) so git_guard
    operations have something real to work against."""

    def _make(repo_path: Path, *, with_content_dirs: bool = True) -> Path:
        repo_path.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
        if with_content_dirs:
            (repo_path / "source").mkdir(exist_ok=True)
            (repo_path / "knowledge").mkdir(exist_ok=True)
            # Git can't track an empty directory; without a placeholder,
            # `git checkout -- source/` has no tracked path to match and
            # fails outright once source/ is genuinely empty again.
            (repo_path / "source" / ".gitkeep").touch()
            (repo_path / "knowledge" / ".gitkeep").touch()
        subprocess.run(["git", "add", "-A"], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "init"], cwd=repo_path, check=True)
        return repo_path

    return _make

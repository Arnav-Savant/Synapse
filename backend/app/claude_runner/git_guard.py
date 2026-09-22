"""Git-based safety net for the knowledge repo (docs/ARCHITECTURE.md §5.4).

Two uses:
- `commit_path`: called right after a new/updated source file is written
  (`services/source_service.py`), so the tree is already clean by the time
  a processing run's `ensure_clean` check runs — a source addition the user
  just made isn't "dirty state", it's the thing about to be processed.
- `ensure_clean`/`finalize`: wrapped around each processing run
  (`services/job_service.py`). The repo must be clean before a run starts;
  after a run, anything touching `source/` is reverted (defense in depth on
  top of `--restricted`/`CLAUDE.md` — instruction-following isn't a hard
  guarantee) and anything touching only `knowledge/`/`assets/` is
  committed, giving every run a real audit trail for free.
"""

import subprocess
from pathlib import Path

# Job bookkeeping (`.synapse/`), CLAUDE.md edits, .gitignore, etc. are
# deliberately out of scope for the clean/revert/commit dance below — this
# guard only cares about the boundary between raw material and generated
# knowledge, not about the repo's overall git status.
_CONTENT_DIRS = ("source/", "knowledge/", "assets/")


class DirtyWorkingTreeError(RuntimeError):
    """The knowledge repo has uncommitted `source/`/`knowledge/`/`assets/`
    changes before a run started."""


class SourceModifiedError(RuntimeError):
    """A processing run touched `source/`; those changes were reverted."""

    def __init__(self, changed_paths: list[str]):
        self.changed_paths = changed_paths
        super().__init__(f"source/ was modified and reverted: {changed_paths}")


def _run_git(repo_path: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo_path), *args],
        capture_output=True,
        text=True,
        check=True,
    )
    return result.stdout


def _changed_content_paths(repo_path: Path) -> list[str]:
    # --untracked-files=all: list files individually even inside a wholly
    # new directory (git's default "normal" mode collapses that to one
    # line, e.g. "?? knowledge/", which would misreport what changed).
    status = _run_git(
        repo_path, "status", "--porcelain", "--untracked-files=all", "--", *_CONTENT_DIRS
    )
    return [line[3:].split(" -> ")[-1] for line in status.splitlines() if line.strip()]


def commit_path(repo_path: Path, relative_path: str, commit_message: str) -> None:
    """Stage and commit a single path. No-op if it has no actual changes
    (e.g. re-saving a source file with identical content)."""
    status = _run_git(repo_path, "status", "--porcelain", "--untracked-files=all", "--", relative_path)
    if not status.strip():
        return
    _run_git(repo_path, "add", "--", relative_path)
    _run_git(repo_path, "commit", "-m", commit_message)


def ensure_clean(repo_path: Path) -> None:
    paths = _changed_content_paths(repo_path)
    if paths:
        raise DirtyWorkingTreeError(str(paths))


def finalize(repo_path: Path, commit_message: str) -> list[str]:
    """Revert anything under `source/`, commit everything else.

    Returns the list of committed (non-source) paths. Raises
    `SourceModifiedError` (after reverting) if `source/` was touched, so the
    caller can still mark the job failed even though the revert succeeded.
    """
    paths = _changed_content_paths(repo_path)
    source_touched = [p for p in paths if p.startswith("source/")]
    other_touched = [p for p in paths if not p.startswith("source/")]

    if other_touched:
        _run_git(repo_path, "add", "--", *other_touched)
        _run_git(repo_path, "commit", "-m", commit_message)

    if source_touched:
        _run_git(repo_path, "checkout", "--", "source/")
        _run_git(repo_path, "clean", "-fd", "--", "source/")
        raise SourceModifiedError(source_touched)

    return other_touched

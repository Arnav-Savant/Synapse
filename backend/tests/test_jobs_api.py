import time

from fastapi.testclient import TestClient

from app.claude_runner import git_guard, runner
from app.claude_runner.runner import ClaudeRunResult
from app.core.config import Settings, get_settings
from app.main import app


def _add_committed_source(repo_path, relative_path: str, content: str) -> None:
    (repo_path / "source" / relative_path).write_text(content)
    git_guard.commit_path(repo_path, f"source/{relative_path}", f"source: add {relative_path}")


def _wait_for_terminal_status(client: TestClient, job_id: str) -> dict:
    for _ in range(100):
        status = client.get(f"/api/jobs/{job_id}").json()
        if status["status"] in ("succeeded", "failed"):
            return status
        time.sleep(0.05)
    raise AssertionError(f"job {job_id} did not reach a terminal state in time")


def test_process_source_job_succeeds_and_commits(tmp_path, monkeypatch, git_repo_factory):
    git_repo_factory(tmp_path)
    _add_committed_source(tmp_path, "chat-001.md", "hello")

    async def fake_run_claude(repo_path, prompt, **kwargs):
        (repo_path / "knowledge" / "concept.md").write_text("# Concept")
        return ClaudeRunResult(
            is_error=False,
            result_text="created concept.md",
            session_id="abc",
            total_cost_usd=0.01,
            permission_denials=[],
        )

    monkeypatch.setattr(runner, "run_claude", fake_run_claude)
    app.dependency_overrides[get_settings] = lambda: Settings(knowledge_repo_path=tmp_path)

    with TestClient(app) as client:
        response = client.post("/api/jobs/process", json={"source_relative_path": "chat-001.md"})
        assert response.status_code == 202

        status = _wait_for_terminal_status(client, response.json()["id"])

    app.dependency_overrides.clear()

    assert status["status"] == "succeeded"
    assert status["committed_files"] == ["knowledge/concept.md"]
    assert status["cost_usd"] == 0.01


def test_process_source_job_reverts_source_changes_and_fails(tmp_path, monkeypatch, git_repo_factory):
    """Simulates the adversarial case: the claude invocation writes to
    source/ (whether by bug or by following an injected instruction from
    the source content). The job must fail and source/ must be untouched."""
    git_repo_factory(tmp_path)
    _add_committed_source(tmp_path, "chat-001.md", "hello")

    async def fake_run_claude(repo_path, prompt, **kwargs):
        (repo_path / "source" / "evil.md").write_text("should not survive")
        return ClaudeRunResult(
            is_error=False,
            result_text="did something it shouldn't have",
            session_id=None,
            total_cost_usd=None,
            permission_denials=[],
        )

    monkeypatch.setattr(runner, "run_claude", fake_run_claude)
    app.dependency_overrides[get_settings] = lambda: Settings(knowledge_repo_path=tmp_path)

    with TestClient(app) as client:
        response = client.post("/api/jobs/process", json={"source_relative_path": "chat-001.md"})
        status = _wait_for_terminal_status(client, response.json()["id"])

    app.dependency_overrides.clear()

    assert status["status"] == "failed"
    assert "source/" in status["error"]
    assert not (tmp_path / "source" / "evil.md").exists()


def test_process_source_job_fails_cleanly_when_claude_errors(tmp_path, monkeypatch, git_repo_factory):
    async def fake_run_claude(repo_path, prompt, **kwargs):
        raise runner.ClaudeRunnerError("simulated failure")

    git_repo_factory(tmp_path)
    _add_committed_source(tmp_path, "chat-001.md", "hello")
    monkeypatch.setattr(runner, "run_claude", fake_run_claude)
    app.dependency_overrides[get_settings] = lambda: Settings(knowledge_repo_path=tmp_path)

    with TestClient(app) as client:
        response = client.post("/api/jobs/process", json={"source_relative_path": "chat-001.md"})
        status = _wait_for_terminal_status(client, response.json()["id"])

    app.dependency_overrides.clear()

    assert status["status"] == "failed"
    assert "simulated failure" in status["error"]


def test_get_unknown_job_returns_404(tmp_path):
    (tmp_path / ".synapse" / "jobs").mkdir(parents=True)
    app.dependency_overrides[get_settings] = lambda: Settings(knowledge_repo_path=tmp_path)

    with TestClient(app) as client:
        response = client.get("/api/jobs/does-not-exist")

    app.dependency_overrides.clear()
    assert response.status_code == 404

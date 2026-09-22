import json
import subprocess

from fastapi.testclient import TestClient

from app.claude_runner import runner
from app.claude_runner.runner import ClaudeRunResult
from app.core.config import Settings, get_settings
from app.main import app

NAMING_MARKER = "Respond with ONLY a single JSON object"


def _fake_run_claude(naming_response: dict | None = None):
    """Every source save now triggers a background processing job, and an
    auto-named save also makes a naming call first — both go through
    `runner.run_claude`, so every test here must mock it or it would spawn
    a real `claude` subprocess in the background."""

    async def fake(repo_path, prompt, **kwargs):
        if NAMING_MARKER in prompt:
            payload = naming_response or {"category": "general", "filename": "untitled"}
            return ClaudeRunResult(
                is_error=False,
                result_text=json.dumps(payload),
                session_id=None,
                total_cost_usd=None,
                permission_denials=[],
            )
        return ClaudeRunResult(
            is_error=False, result_text="processed", session_id=None, total_cost_usd=None, permission_denials=[]
        )

    return fake


def _client_for(tmp_path, git_repo_factory, monkeypatch, naming_response: dict | None = None) -> TestClient:
    git_repo_factory(tmp_path)
    monkeypatch.setattr(runner, "run_claude", _fake_run_claude(naming_response))
    app.dependency_overrides[get_settings] = lambda: Settings(knowledge_repo_path=tmp_path)
    return TestClient(app)


def test_create_and_list_source(tmp_path, git_repo_factory, monkeypatch):
    client = _client_for(tmp_path, git_repo_factory, monkeypatch)

    response = client.post(
        "/api/sources",
        json={"category": "prompt-engineering", "filename": "chat-001", "content": "hello"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["source"]["filename"] == "chat-001.md"
    assert body["job_id"]

    listing = client.get("/api/sources")
    assert listing.status_code == 200
    assert len(listing.json()["sources"]) == 1

    app.dependency_overrides.clear()


def test_create_source_with_explicit_name_skips_naming_call(tmp_path, git_repo_factory, monkeypatch):
    calls = []

    async def tracking_fake(repo_path, prompt, **kwargs):
        calls.append(prompt)
        return ClaudeRunResult(
            is_error=False, result_text="processed", session_id=None, total_cost_usd=None, permission_denials=[]
        )

    client = _client_for(tmp_path, git_repo_factory, monkeypatch)
    monkeypatch.setattr(runner, "run_claude", tracking_fake)

    client.post(
        "/api/sources",
        json={"category": "prompt-engineering", "filename": "chat-001", "content": "hello"},
    )

    assert not any(NAMING_MARKER in call for call in calls)

    app.dependency_overrides.clear()


def test_create_source_with_auto_naming(tmp_path, git_repo_factory, monkeypatch):
    client = _client_for(
        tmp_path, git_repo_factory, monkeypatch, naming_response={"category": "rag", "filename": "hybrid-search"}
    )

    response = client.post("/api/sources", json={"content": "some raw pasted content about RAG"})

    assert response.status_code == 201
    source = response.json()["source"]
    assert source["category"] == "rag"
    assert source["filename"] == "hybrid-search.md"
    assert (tmp_path / "source" / "rag" / "hybrid-search.md").read_text() == "some raw pasted content about RAG"

    app.dependency_overrides.clear()


def test_auto_naming_avoids_overwriting_an_existing_file(tmp_path, git_repo_factory, monkeypatch):
    client = _client_for(
        tmp_path, git_repo_factory, monkeypatch, naming_response={"category": "rag", "filename": "hybrid-search"}
    )

    first = client.post("/api/sources", json={"content": "first version"})
    second = client.post("/api/sources", json={"content": "second, unrelated content"})

    assert first.json()["source"]["filename"] == "hybrid-search.md"
    assert second.json()["source"]["filename"] == "hybrid-search-2.md"
    assert (tmp_path / "source" / "rag" / "hybrid-search.md").read_text() == "first version"
    assert (tmp_path / "source" / "rag" / "hybrid-search-2.md").read_text() == "second, unrelated content"

    app.dependency_overrides.clear()


def test_create_source_is_committed_to_git(tmp_path, git_repo_factory, monkeypatch):
    """Regression test: a newly created source file must be committed
    immediately, or the very next processing job's `ensure_clean` check
    would reject it as uncommitted state (found via live end-to-end testing
    in Phase 2). Scoped to source/knowledge/assets — the auto-triggered
    processing job's own `.synapse/jobs/*.json` record is expected to be
    untracked at this point; that's operational state, not content."""
    client = _client_for(tmp_path, git_repo_factory, monkeypatch)

    client.post(
        "/api/sources",
        json={"category": "prompt-engineering", "filename": "chat-001", "content": "hello"},
    )

    status = subprocess.run(
        ["git", "status", "--porcelain", "--", "source/", "knowledge/", "assets/"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        check=True,
    )
    assert status.stdout.strip() == ""

    app.dependency_overrides.clear()


def test_source_path_traversal_rejected_with_4xx(tmp_path, git_repo_factory, monkeypatch):
    client = _client_for(tmp_path, git_repo_factory, monkeypatch)

    response = client.post(
        "/api/sources",
        json={"category": "../../etc", "filename": "passwd", "content": "x"},
    )

    assert 400 <= response.status_code < 500
    assert not (tmp_path.parent.parent / "etc" / "passwd").exists()

    app.dependency_overrides.clear()


def test_get_source_content(tmp_path, git_repo_factory, monkeypatch):
    client = _client_for(tmp_path, git_repo_factory, monkeypatch)
    client.post(
        "/api/sources",
        json={"category": "prompt-engineering", "filename": "chat-001", "content": "hello world"},
    )

    response = client.get("/api/sources/prompt-engineering/chat-001.md")

    assert response.status_code == 200
    assert response.json() == {
        "relative_path": "prompt-engineering/chat-001.md",
        "content": "hello world",
    }

    app.dependency_overrides.clear()


def test_get_missing_source_content_returns_404(tmp_path, git_repo_factory, monkeypatch):
    client = _client_for(tmp_path, git_repo_factory, monkeypatch)

    response = client.get("/api/sources/does-not-exist.md")

    assert response.status_code == 404

    app.dependency_overrides.clear()

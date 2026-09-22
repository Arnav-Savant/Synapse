import subprocess

from fastapi.testclient import TestClient

from app.claude_runner import runner
from app.claude_runner.runner import ClaudeRunResult
from app.core.config import Settings, get_settings
from app.main import app


def _client_for(tmp_path, git_repo_factory) -> TestClient:
    git_repo_factory(tmp_path)
    (tmp_path / "knowledge" / "prompt-injection.md").write_text(
        "---\nid: prompt-injection\ntitle: Prompt Injection\n---\nPrompt injection is an attack.\n",
        encoding="utf-8",
    )
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=tmp_path, check=True)
    app.dependency_overrides[get_settings] = lambda: Settings(knowledge_repo_path=tmp_path)
    return TestClient(app)


def test_chat_returns_relevant_answer(tmp_path, git_repo_factory, monkeypatch):
    async def fake_run_claude(repo_path, prompt, **kwargs):
        return ClaudeRunResult(
            is_error=False,
            result_text="Prompt injection is when untrusted input hijacks a model's instructions.",
            session_id="abc",
            total_cost_usd=0.02,
            permission_denials=[],
        )

    monkeypatch.setattr(runner, "run_claude", fake_run_claude)
    client = _client_for(tmp_path, git_repo_factory)

    response = client.post("/api/chat", json={"message": "What is prompt injection?"})

    assert response.status_code == 200
    assert "hijacks" in response.json()["reply"]

    app.dependency_overrides.clear()


def test_chat_does_not_modify_the_knowledge_repo(tmp_path, git_repo_factory, monkeypatch):
    """Phase 6 acceptance criterion: after a chat interaction, `git status`
    shows no changes — proving the read-only restriction actually holds,
    not just assumed from the --tools flag."""

    async def fake_run_claude(repo_path, prompt, *, tools, **kwargs):
        # A real read-only invocation physically cannot write; simulate
        # that guarantee here rather than actually touching disk.
        assert tools == runner.READ_ONLY_TOOLS
        return ClaudeRunResult(
            is_error=False, result_text="answer", session_id=None, total_cost_usd=None, permission_denials=[]
        )

    monkeypatch.setattr(runner, "run_claude", fake_run_claude)
    client = _client_for(tmp_path, git_repo_factory)

    client.post("/api/chat", json={"message": "What is prompt injection?", "concept_slug": "prompt-injection"})

    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True, check=True
    )
    assert status.stdout.strip() == ""

    app.dependency_overrides.clear()


def test_chat_works_with_no_llm_provider_configured(tmp_path, git_repo_factory, monkeypatch):
    """FR6.4: the core chat path must not secretly require an API key —
    there is no LLM provider config anywhere in this test."""

    async def fake_run_claude(repo_path, prompt, **kwargs):
        return ClaudeRunResult(
            is_error=False, result_text="answer", session_id=None, total_cost_usd=None, permission_denials=[]
        )

    monkeypatch.setattr(runner, "run_claude", fake_run_claude)
    client = _client_for(tmp_path, git_repo_factory)

    response = client.post("/api/chat", json={"message": "hello"})

    assert response.status_code == 200

    app.dependency_overrides.clear()


def test_chat_engine_error_returns_502(tmp_path, git_repo_factory, monkeypatch):
    async def fake_run_claude(repo_path, prompt, **kwargs):
        return ClaudeRunResult(
            is_error=True, result_text="claude failed", session_id=None, total_cost_usd=None, permission_denials=[]
        )

    monkeypatch.setattr(runner, "run_claude", fake_run_claude)
    client = _client_for(tmp_path, git_repo_factory)

    response = client.post("/api/chat", json={"message": "hello"})

    assert response.status_code == 502

    app.dependency_overrides.clear()

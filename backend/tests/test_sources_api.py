import subprocess

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app


def _client_for(tmp_path, git_repo_factory) -> TestClient:
    git_repo_factory(tmp_path)
    app.dependency_overrides[get_settings] = lambda: Settings(knowledge_repo_path=tmp_path)
    return TestClient(app)


def test_create_and_list_source(tmp_path, git_repo_factory):
    client = _client_for(tmp_path, git_repo_factory)

    response = client.post(
        "/api/sources",
        json={"category": "prompt-engineering", "filename": "chat-001", "content": "hello"},
    )
    assert response.status_code == 201
    assert response.json()["filename"] == "chat-001.md"

    listing = client.get("/api/sources")
    assert listing.status_code == 200
    assert len(listing.json()["sources"]) == 1

    app.dependency_overrides.clear()


def test_create_source_is_committed_to_git(tmp_path, git_repo_factory):
    """Regression test: a newly created source file must be committed
    immediately, or the very next processing job's `ensure_clean` check
    would reject it as uncommitted state (found via live end-to-end testing
    in Phase 2)."""
    client = _client_for(tmp_path, git_repo_factory)

    client.post(
        "/api/sources",
        json={"category": "prompt-engineering", "filename": "chat-001", "content": "hello"},
    )

    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True, check=True
    )
    assert status.stdout.strip() == ""

    app.dependency_overrides.clear()


def test_source_path_traversal_rejected_with_4xx(tmp_path, git_repo_factory):
    client = _client_for(tmp_path, git_repo_factory)

    response = client.post(
        "/api/sources",
        json={"category": "../../etc", "filename": "passwd", "content": "x"},
    )

    assert 400 <= response.status_code < 500
    assert not (tmp_path.parent.parent / "etc" / "passwd").exists()

    app.dependency_overrides.clear()

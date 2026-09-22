from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app


def _client_for(tmp_path) -> TestClient:
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "prompt-injection.md").write_text("# Prompt Injection", encoding="utf-8")
    app.dependency_overrides[get_settings] = lambda: Settings(knowledge_repo_path=tmp_path)
    return TestClient(app)


def test_list_and_get_knowledge(tmp_path):
    client = _client_for(tmp_path)

    listing = client.get("/api/knowledge")
    assert listing.status_code == 200
    assert listing.json()["slugs"] == ["prompt-injection"]

    detail = client.get("/api/knowledge/prompt-injection")
    assert detail.status_code == 200
    assert detail.json()["content"] == "# Prompt Injection"

    app.dependency_overrides.clear()


def test_get_missing_knowledge_returns_404(tmp_path):
    client = _client_for(tmp_path)

    response = client.get("/api/knowledge/does-not-exist")

    assert response.status_code == 404

    app.dependency_overrides.clear()

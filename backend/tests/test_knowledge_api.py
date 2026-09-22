import subprocess
from datetime import date

from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app
from app.services import graph_service

CONCEPT_MD = """---
id: prompt-injection
title: Prompt Injection
aliases: ["Prompt Injection Attack"]
domains: [prompt-engineering, ai-security]
status: developing
created: 2026-09-22
updated: 2026-09-22
sources: [prompt-engineering/chat-001.md]
relationships:
  - type: subtopic-of
    target: prompt-engineering
    note: some note
---

Body with a [[prompt-engineering]] link.
"""


def _client_for(tmp_path, git_repo_factory) -> TestClient:
    git_repo_factory(tmp_path)
    (tmp_path / "knowledge" / "prompt-injection.md").write_text(CONCEPT_MD, encoding="utf-8")
    (tmp_path / "knowledge" / "prompt-engineering.md").write_text(
        "---\nid: prompt-engineering\ntitle: Prompt Engineering\n---\nbody\n", encoding="utf-8"
    )
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
    subprocess.run(["git", "commit", "-q", "-m", "seed"], cwd=tmp_path, check=True)

    app.dependency_overrides[get_settings] = lambda: Settings(knowledge_repo_path=tmp_path)
    return TestClient(app)


def test_list_and_get_knowledge(tmp_path, git_repo_factory):
    client = _client_for(tmp_path, git_repo_factory)

    listing = client.get("/api/knowledge")
    assert listing.status_code == 200
    assert set(listing.json()["slugs"]) == {"prompt-injection", "prompt-engineering"}

    detail = client.get("/api/knowledge/prompt-injection")
    assert detail.status_code == 200
    body = detail.json()
    assert body["title"] == "Prompt Injection"
    assert body["aliases"] == ["Prompt Injection Attack"]
    assert body["domains"] == ["prompt-engineering", "ai-security"]
    assert body["status"] == "developing"
    assert body["relationships"] == [
        {"type": "subtopic-of", "target": "prompt-engineering", "note": "some note"}
    ]
    assert "Body with a [[prompt-engineering]] link." in body["body"]
    assert body["raw_content"] == CONCEPT_MD

    app.dependency_overrides.clear()


def test_get_missing_knowledge_returns_404(tmp_path, git_repo_factory):
    client = _client_for(tmp_path, git_repo_factory)

    response = client.get("/api/knowledge/does-not-exist")

    assert response.status_code == 404

    app.dependency_overrides.clear()


def test_get_malformed_knowledge_returns_400(tmp_path, git_repo_factory):
    client = _client_for(tmp_path, git_repo_factory)
    (tmp_path / "knowledge" / "broken.md").write_text("no frontmatter here", encoding="utf-8")

    response = client.get("/api/knowledge/broken")

    assert response.status_code == 400

    app.dependency_overrides.clear()


def test_update_knowledge_round_trips_and_commits(tmp_path, git_repo_factory):
    client = _client_for(tmp_path, git_repo_factory)
    graph_service.invalidate(tmp_path)

    new_content = CONCEPT_MD.replace("Body with a", "Updated body with a")
    response = client.put("/api/knowledge/prompt-injection", json={"content": new_content})

    assert response.status_code == 200
    body = response.json()
    assert "Updated body with a" in body["body"]
    # updated is auto-refreshed regardless of what the client sent
    assert body["updated"] == date.today().isoformat()

    # Persisted to disk.
    on_disk = (tmp_path / "knowledge" / "prompt-injection.md").read_text(encoding="utf-8")
    assert "Updated body with a" in on_disk

    # Committed — tree is clean, matching the source-write behavior from Phase 2.
    status = subprocess.run(
        ["git", "status", "--porcelain"], cwd=tmp_path, capture_output=True, text=True, check=True
    )
    assert status.stdout.strip() == ""

    app.dependency_overrides.clear()


def test_update_knowledge_rejects_id_mismatch(tmp_path, git_repo_factory):
    client = _client_for(tmp_path, git_repo_factory)

    response = client.put(
        "/api/knowledge/prompt-injection",
        json={"content": "---\nid: some-other-id\ntitle: X\n---\nbody\n"},
    )

    assert response.status_code == 400

    app.dependency_overrides.clear()


def test_update_knowledge_invalidates_graph_cache(tmp_path, git_repo_factory):
    client = _client_for(tmp_path, git_repo_factory)
    graph_service.invalidate(tmp_path)

    graph_before = graph_service.get_graph(tmp_path)
    assert len(graph_before.edges) == 1  # the subtopic-of relationship

    new_content = (
        CONCEPT_MD.replace("  - type: subtopic-of\n    target: prompt-engineering\n    note: some note\n", "")
        .replace("Body with a [[prompt-engineering]] link.", "Body with no links now.")
    )
    client.put("/api/knowledge/prompt-injection", json={"content": new_content})

    graph_after = graph_service.get_graph(tmp_path)
    assert len(graph_after.edges) == 0

    app.dependency_overrides.clear()

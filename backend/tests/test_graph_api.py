from fastapi.testclient import TestClient

from app.core.config import Settings, get_settings
from app.main import app
from app.services import graph_service


def _write_concept(knowledge_dir, slug: str, title: str, body: str = "") -> None:
    (knowledge_dir / f"{slug}.md").write_text(
        f"""---
id: {slug}
title: {title}
---
# {title}

{body}
""",
        encoding="utf-8",
    )


def test_get_graph_returns_nodes_and_edges(tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    _write_concept(knowledge_dir, "prompt-engineering", "Prompt Engineering")
    _write_concept(
        knowledge_dir,
        "few-shot-prompting",
        "Few-Shot Prompting",
        body="See [[prompt-engineering]].",
    )

    graph_service.invalidate(tmp_path)
    app.dependency_overrides[get_settings] = lambda: Settings(knowledge_repo_path=tmp_path)

    with TestClient(app) as client:
        response = client.get("/api/graph")

    app.dependency_overrides.clear()

    assert response.status_code == 200
    body = response.json()
    assert {n["id"] for n in body["nodes"]} == {"prompt-engineering", "few-shot-prompting"}
    assert len(body["edges"]) == 1
    assert body["edges"][0]["implicit"] is True
    assert body["warnings"] == []

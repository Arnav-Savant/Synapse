from app.services import graph_service


def _write_concept(knowledge_dir, slug: str, title: str, relationships: str = "") -> None:
    (knowledge_dir / f"{slug}.md").write_text(
        f"""---
id: {slug}
title: {title}
relationships:
{relationships}
---
# {title}
""",
        encoding="utf-8",
    )


def test_get_graph_reflects_new_file_without_restart(tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    _write_concept(knowledge_dir, "prompt-engineering", "Prompt Engineering")

    graph = graph_service.get_graph(tmp_path)
    assert {n.id for n in graph.nodes} == {"prompt-engineering"}

    graph_service.invalidate(tmp_path)
    _write_concept(knowledge_dir, "few-shot-prompting", "Few-Shot Prompting")

    graph_again = graph_service.get_graph(tmp_path)
    assert {n.id for n in graph_again.nodes} == {"prompt-engineering", "few-shot-prompting"}


def test_get_graph_caches_until_invalidated(tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    _write_concept(knowledge_dir, "prompt-engineering", "Prompt Engineering")

    graph_service.get_graph(tmp_path)
    _write_concept(knowledge_dir, "few-shot-prompting", "Few-Shot Prompting")

    # Not invalidated yet — should still reflect the cached (stale) state.
    stale_graph = graph_service.get_graph(tmp_path)
    assert {n.id for n in stale_graph.nodes} == {"prompt-engineering"}

    graph_service.invalidate(tmp_path)
    fresh_graph = graph_service.get_graph(tmp_path)
    assert {n.id for n in fresh_graph.nodes} == {"prompt-engineering", "few-shot-prompting"}


def test_get_graph_skips_malformed_file_with_warning(tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    _write_concept(knowledge_dir, "prompt-engineering", "Prompt Engineering")
    (knowledge_dir / "broken.md").write_text("not even frontmatter", encoding="utf-8")

    graph = graph_service.get_graph(tmp_path)

    assert {n.id for n in graph.nodes} == {"prompt-engineering"}
    assert any("broken" in w for w in graph.warnings)

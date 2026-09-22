import pytest

from app.repositories import knowledge_repo


def test_list_and_read_knowledge(tmp_path):
    knowledge_dir = tmp_path / "knowledge"
    knowledge_dir.mkdir()
    (knowledge_dir / "prompt-injection.md").write_text("# Prompt Injection", encoding="utf-8")
    (knowledge_dir / ".gitkeep").write_text("", encoding="utf-8")

    slugs = knowledge_repo.list_knowledge_slugs(tmp_path)
    assert slugs == ["prompt-injection"]

    content = knowledge_repo.read_knowledge(tmp_path, "prompt-injection")
    assert content == "# Prompt Injection"


def test_read_missing_knowledge_raises(tmp_path):
    (tmp_path / "knowledge").mkdir()

    with pytest.raises(knowledge_repo.KnowledgeFileNotFoundError):
        knowledge_repo.read_knowledge(tmp_path, "does-not-exist")


def test_list_knowledge_on_missing_dir_returns_empty(tmp_path):
    assert knowledge_repo.list_knowledge_slugs(tmp_path) == []

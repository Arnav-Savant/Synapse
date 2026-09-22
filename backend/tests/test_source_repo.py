from app.repositories import source_repo


def test_write_and_list_text_source(tmp_path):
    (tmp_path / "source").mkdir()

    written = source_repo.write_text_source(tmp_path, "prompt-engineering", "chat-001.md", "# Hello")

    assert written.category == "prompt-engineering"
    assert written.filename == "chat-001.md"
    assert written.relative_path == "prompt-engineering/chat-001.md"

    listed = source_repo.list_sources(tmp_path)

    assert len(listed) == 1
    assert listed[0].relative_path == "prompt-engineering/chat-001.md"
    assert (tmp_path / "source" / "prompt-engineering" / "chat-001.md").read_text() == "# Hello"


def test_write_text_source_overwrites_existing(tmp_path):
    (tmp_path / "source").mkdir()
    source_repo.write_text_source(tmp_path, "llm", "chat-001.md", "first")

    source_repo.write_text_source(tmp_path, "llm", "chat-001.md", "second")

    assert (tmp_path / "source" / "llm" / "chat-001.md").read_text() == "second"
    assert len(source_repo.list_sources(tmp_path)) == 1


def test_write_binary_source_goes_to_uploads(tmp_path):
    (tmp_path / "source").mkdir()

    written = source_repo.write_binary_source(tmp_path, "paper.pdf", b"%PDF-1.4")

    assert written.category == "_uploads"
    assert (tmp_path / "source" / "_uploads" / "paper.pdf").read_bytes() == b"%PDF-1.4"


def test_list_sources_ignores_gitkeep_and_missing_dir(tmp_path):
    assert source_repo.list_sources(tmp_path) == []

    source_dir = tmp_path / "source"
    source_dir.mkdir()
    (source_dir / ".gitkeep").write_text("")

    assert source_repo.list_sources(tmp_path) == []

from app.jobs import store


def test_create_and_load_job(tmp_path):
    job = store.create_job(tmp_path, "prompt-engineering/chat-001.md")

    assert job.status == "queued"

    loaded = store.load_job(tmp_path, job.id)
    assert loaded is not None
    assert loaded.source_relative_path == "prompt-engineering/chat-001.md"


def test_load_missing_job_returns_none(tmp_path):
    assert store.load_job(tmp_path, "does-not-exist") is None


def test_list_jobs_on_missing_dir_returns_empty(tmp_path):
    assert store.list_jobs(tmp_path) == []


def test_list_jobs_returns_all_created_jobs(tmp_path):
    first = store.create_job(tmp_path, "a.md")
    second = store.create_job(tmp_path, "b.md")

    ids = {job.id for job in store.list_jobs(tmp_path)}

    assert ids == {first.id, second.id}


def test_reconcile_orphaned_running_jobs_marks_them_failed(tmp_path):
    job = store.create_job(tmp_path, "a.md")
    job.status = "running"
    store.save_job(tmp_path, job)

    reconciled = store.reconcile_orphaned_running_jobs(tmp_path)

    assert [j.id for j in reconciled] == [job.id]
    loaded = store.load_job(tmp_path, job.id)
    assert loaded.status == "failed"
    assert "restarted" in loaded.error


def test_reconcile_leaves_terminal_jobs_alone(tmp_path):
    job = store.create_job(tmp_path, "a.md")
    job.status = "succeeded"
    store.save_job(tmp_path, job)

    reconciled = store.reconcile_orphaned_running_jobs(tmp_path)

    assert reconciled == []
    assert store.load_job(tmp_path, job.id).status == "succeeded"

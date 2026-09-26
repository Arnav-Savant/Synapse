"""Shared pytest fixtures."""

import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from app.core.postgres_connection import postgres_connection

_BACKEND_DIR = Path(__file__).resolve().parent.parent  # tests/conftest.py -> tests/ -> backend/
_ALEMBIC_INI = _BACKEND_DIR / "alembic.ini"


@pytest.fixture(scope="session")
async def _migrated_engine() -> AsyncIterator[AsyncEngine]:
    """Puts the test Postgres DB through the real Alembic migrations exactly
    once per test session, instead of every Postgres-touching test file
    running its own `Base.metadata.create_all`/`drop_all` against the
    shared `postgres_connection` singleton `AsyncEngine` — that per-file
    schema recreation, repeated across a growing number of test files under
    the session-scoped event loop (see `pyproject.toml`'s
    `asyncio_default_fixture_loop_scope` comment), was corrupting the
    connection pool (`asyncpg.exceptions.InterfaceError: cannot perform
    operation: another operation is in progress`) as test volume grew.

    The schema is dropped and recreated from scratch first (rather than
    trusting `alembic upgrade head` alone) because this engine also backs
    the real dev DB used by `TestClient`/`lifespan`-driven API tests
    (e.g. `test_agent_config_api.py`), which can leave `alembic_version`
    stamped at head with tables that a stale `drop_all`-based fixture (the
    pattern this replaces) already dropped — `upgrade head` against that
    state is a no-op and leaves the schema missing, confirmed empirically.
    """
    engine = postgres_connection.get_engine()
    async with engine.begin() as conn:
        await conn.execute(text("DROP SCHEMA public CASCADE"))
        await conn.execute(text("CREATE SCHEMA public"))
    subprocess.run(
        ["alembic", "-c", str(_ALEMBIC_INI), "upgrade", "head"],
        check=True,
        cwd=_BACKEND_DIR,
    )
    yield engine
    await engine.dispose()


@pytest.fixture
async def db_session(_migrated_engine: AsyncEngine) -> AsyncIterator[AsyncSession]:
    """One test = one transaction that's rolled back at teardown, instead of
    the old per-file create_all/drop_all pattern. The session is bound to a
    connection with `join_transaction_mode="create_savepoint"`, so it runs
    on a SAVEPOINT nested inside this fixture's outer transaction: a repo
    function's internal `await session.commit()` (e.g.
    `concept_repo.create_concept`) only releases that savepoint rather than
    ending the outer transaction, and autobegin opens a fresh savepoint for
    whatever the test does next. The final `conn.rollback()` below always
    discards the outer transaction, so nothing a test commits is ever
    visible to another test or left behind in the DB (verified empirically:
    two sequential committing calls within one test both roll back at
    teardown, and a second test never sees the first test's data)."""
    async with _migrated_engine.connect() as conn:
        await conn.begin()
        session_factory = async_sessionmaker(
            bind=conn, expire_on_commit=False, join_transaction_mode="create_savepoint"
        )
        async with session_factory() as session:
            yield session
        await conn.rollback()


@pytest.fixture
def git_repo_factory():
    """Returns a callable that git-inits a directory (with a usable local
    user config, and the standard source/knowledge dirs) so git_guard
    operations have something real to work against."""

    def _make(repo_path: Path, *, with_content_dirs: bool = True) -> Path:
        repo_path.mkdir(parents=True, exist_ok=True)
        subprocess.run(["git", "init", "-q"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=repo_path, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=repo_path, check=True)
        if with_content_dirs:
            (repo_path / "source").mkdir(exist_ok=True)
            (repo_path / "knowledge").mkdir(exist_ok=True)
            # Git can't track an empty directory; without a placeholder,
            # `git checkout -- source/` has no tracked path to match and
            # fails outright once source/ is genuinely empty again.
            (repo_path / "source" / ".gitkeep").touch()
            (repo_path / "knowledge" / ".gitkeep").touch()
        subprocess.run(["git", "add", "-A"], cwd=repo_path, check=True)
        subprocess.run(["git", "commit", "-q", "--allow-empty", "-m", "init"], cwd=repo_path, check=True)
        return repo_path

    return _make

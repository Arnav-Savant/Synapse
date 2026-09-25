"""Application configuration, loaded once from environment/.env.

This is the only module that reads environment variables directly; every
other module receives configuration through this settings object (or a
FastAPI dependency derived from it), never via `os.environ` calls of its
own.
"""

import os
from functools import lru_cache
from pathlib import Path
from typing import TypeVar

from dotenv import load_dotenv

load_dotenv()


# backend/app/core/config.py -> parents[3] is the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]

T = TypeVar("T")


def _resolve(value: T | None, env_var: str, default: T, cast=str) -> T:
    """Precedence: explicit kwarg > env var (cast) > default. `is None` checks
    throughout so a legitimately falsy override (e.g. port=0) is never
    mistaken for "not provided"."""
    if value is not None:
        return value
    raw = os.environ.get(env_var)
    return cast(raw) if raw is not None else default


class ServerConfig:
    def __init__(
        self,
        knowledge_repo_path: Path | None = None,
        frontend_origin: str | None = None,
        database_host: str | None = None,
        database_port: int | None = None,
        database_user: str | None = None,
        database_password: str | None = None,
        database_name: str | None = None,
        app_host: str | None = None,
        app_port: int | None = None,
        kuzu_db_path: Path | None = None,
        log_level: str | None = None,
    ) -> None:
        self.knowledge_repo_path = _resolve(
            knowledge_repo_path, "KNOWLEDGE_REPO_PATH", _REPO_ROOT / "synapse-knowledge", Path
        )

        # Frontend dev server origin, allowed for CORS. Backend itself only
        # binds to 127.0.0.1 (see SETUP.md) — no other origins are permitted.
        self.frontend_origin = _resolve(frontend_origin, "FRONTEND_ORIGIN", "http://localhost:5173")

        self.database_host = _resolve(database_host, "DATABASE_HOST", "localhost")
        self.database_port = _resolve(database_port, "DATABASE_PORT", 5432, int)
        self.database_user = _resolve(database_user, "DATABASE_USER", "synapse")
        self.database_password = _resolve(database_password, "DATABASE_PASSWORD", "synapse")
        self.database_name = _resolve(database_name, "DATABASE_NAME", "synapse")

        self.app_host = _resolve(app_host, "APP_HOST", "127.0.0.1")
        self.app_port = _resolve(app_port, "APP_PORT", 8000, int)

        self.kuzu_db_path = _resolve(kuzu_db_path, "KUZU_DB_PATH", _REPO_ROOT / ".synapse-graph", Path)

        self.log_level = _resolve(log_level, "LOG_LEVEL", "INFO").upper()

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.database_user}:{self.database_password}"
            f"@{self.database_host}:{self.database_port}/{self.database_name}"
        )


@lru_cache
def get_server_config() -> ServerConfig:
    return ServerConfig()


def get_env_var(name: str) -> str | None:
    return os.environ.get(name)

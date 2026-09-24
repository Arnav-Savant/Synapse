"""Application configuration, loaded once from environment/.env.

This is the only module that reads environment variables directly; every
other module receives configuration through this settings object (or a
FastAPI dependency derived from it), never via `os.environ` calls of its
own.
"""

import os
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


# backend/app/core/config.py -> parents[3] is the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    knowledge_repo_path: Path = _REPO_ROOT / "synapse-knowledge"

    # Frontend dev server origin, allowed for CORS. Backend itself only
    # binds to 127.0.0.1 (see SETUP.md) — no other origins are permitted.
    frontend_origin: str = "http://localhost:5173"

    database_url: str = "postgresql+asyncpg://synapse:synapse@localhost:5432/synapse"
    kuzu_db_path: Path = _REPO_ROOT / ".synapse-graph"


@lru_cache
def get_settings() -> Settings:
    return Settings()


def get_env_var(name: str) -> str | None:
    return os.environ.get(name)

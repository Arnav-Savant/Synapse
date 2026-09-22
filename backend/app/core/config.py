"""Application configuration, loaded once from environment/.env.

This is the only module that reads environment variables directly; every
other module receives configuration through this settings object (or a
FastAPI dependency derived from it), never via `os.environ` calls of its
own.
"""

from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    knowledge_repo_path: Path = Path("~/synapse-knowledge").expanduser()

    # Frontend dev server origin, allowed for CORS. Backend itself only
    # binds to 127.0.0.1 (see SETUP.md) — no other origins are permitted.
    frontend_origin: str = "http://localhost:5173"


@lru_cache
def get_settings() -> Settings:
    return Settings()

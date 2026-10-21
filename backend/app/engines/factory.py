"""Builds the one agent engine the app uses."""

import contextlib

from app.core.postgres_connection import postgres_connection
from app.engines.claude_code_engine import ClaudeCodeEngine


def build_engine() -> ClaudeCodeEngine:
    return ClaudeCodeEngine(contextlib.asynccontextmanager(postgres_connection.get_session))

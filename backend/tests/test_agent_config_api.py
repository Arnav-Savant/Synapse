"""Matches `test_jobs_api.py`/`test_chat_api.py`'s `TestClient`/`lifespan`
convention (`with TestClient(app) as client:`, so migrations + agent-config
seeding actually run), with one deliberate difference: this file shares a
single `TestClient` (module-scoped fixture) across all its tests instead of
opening a fresh one per test function. The `agent_configs` table is real,
persistent Postgres state — unlike `test_jobs_api.py`/`test_chat_api.py`,
whose requests never touch the DB via `Depends`, every request here does,
and repeatedly entering/exiting `TestClient(app)` (a fresh thread + event
loop each time) against the single module-level `postgres_connection`
engine reuses pooled asyncpg connections bound to an already-closed loop,
which asyncpg fails on (confirmed empirically — this reproduces even in
`test_jobs_api.py` unmodified, so it's a pre-existing engine-lifecycle gap,
not something to silently work around by disposing the shared engine from
inside a test). One shared client for the whole module sidesteps it
entirely. Each test below only touches a role no other test in this file
touches, so tests stay independent of execution order regardless.
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app

_SEEDED_ROLES = {"orchestrator", "text_agent", "graph_agent", "validation_agent", "naming", "chat"}


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as test_client:
        yield test_client


def test_list_agent_configs_returns_the_6_seeded_roles(client: TestClient):
    response = client.get("/api/agent-configs")

    assert response.status_code == 200
    roles = {c["agent_role"] for c in response.json()["configs"]}
    assert roles == _SEEDED_ROLES


def test_update_agent_config_roundtrips(client: TestClient):
    put_response = client.put(
        "/api/agent-configs/chat",
        json={"engine": "claude_code", "model": "claude-opus-5-5", "effort": "high"},
    )
    assert put_response.status_code == 200
    assert put_response.json()["model"] == "claude-opus-5-5"

    get_response = client.get("/api/agent-configs")

    updated = next(c for c in get_response.json()["configs"] if c["agent_role"] == "chat")
    assert updated["engine"] == "claude_code"
    assert updated["model"] == "claude-opus-5-5"
    assert updated["effort"] == "high"


def test_update_agent_config_invalid_engine_returns_400(client: TestClient):
    response = client.put(
        "/api/agent-configs/text_agent",
        json={"engine": "ollama", "model": "llama3", "effort": "medium"},
    )

    assert response.status_code == 400
    assert "engine" in response.json()["detail"]


def test_update_agent_config_litellm_unset_env_var_returns_400(client: TestClient, monkeypatch):
    monkeypatch.delenv("SOME_UNSET_API_KEY", raising=False)

    response = client.put(
        "/api/agent-configs/naming",
        json={
            "engine": "litellm",
            "model": "gpt-5",
            "effort": "high",
            "provider": "openai",
            "env_key_name": "SOME_UNSET_API_KEY",
        },
    )

    assert response.status_code == 400
    assert "SOME_UNSET_API_KEY not set" in response.json()["detail"]


def test_update_agent_config_unknown_role_returns_404(client: TestClient):
    response = client.put(
        "/api/agent-configs/does-not-exist",
        json={"engine": "claude_code", "model": "claude-sonnet-5", "effort": "medium"},
    )

    assert response.status_code == 404

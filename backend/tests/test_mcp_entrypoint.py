"""Unit tests for the MCP server subprocess entrypoint. Per ARCHITECTURE.md
§12, this does not spawn a real subprocess or run a real stdio server —
`SynapseMcpServer` is stubbed and `main()` is called directly with explicit
argv."""

import pytest

from app.mcp_server.server import AgentRole


def test_main_constructs_server_with_parsed_args_and_runs_stdio(monkeypatch):
    constructed = {}

    class StubServer:
        def __init__(self, role, job_id):
            constructed["role"] = role
            constructed["job_id"] = job_id

        def run_stdio(self):
            constructed["ran"] = True

    monkeypatch.setattr("app.mcp_server.entrypoint.SynapseMcpServer", StubServer)
    from app.mcp_server.entrypoint import main

    main(["--role", "text_agent", "--job-id", "job-1"])

    assert constructed["role"] == AgentRole.TEXT_AGENT
    assert constructed["job_id"] == "job-1"
    assert constructed["ran"] is True


def test_main_rejects_invalid_role(monkeypatch):
    class StubServer:
        def __init__(self, role, job_id):
            pass

        def run_stdio(self):
            pass

    monkeypatch.setattr("app.mcp_server.entrypoint.SynapseMcpServer", StubServer)
    from app.mcp_server.entrypoint import main

    with pytest.raises(ValueError):
        main(["--role", "not_a_real_role", "--job-id", "job-1"])

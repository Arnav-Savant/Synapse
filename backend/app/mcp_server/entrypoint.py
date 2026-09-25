"""Subprocess entrypoint for SynapseMcpServer — what `claude -p`'s
`--mcp-config` mechanism actually spawns (command=<python>, args=[this
file, "--role", ..., "--job-id", ...]). Self-locates the backend root via
__file__ rather than relying on cwd, which the CLI does not honor for
MCP server subprocess launches (confirmed empirically)."""

import argparse
import sys
from pathlib import Path

# backend/app/mcp_server/entrypoint.py -> parents[2] is backend/
_BACKEND_DIR = Path(__file__).resolve().parents[2]
if str(_BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(_BACKEND_DIR))

from app.mcp_server.server import AgentRole, SynapseMcpServer  # noqa: E402 — must follow sys.path fix


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--role", required=True)
    parser.add_argument("--job-id", required=True)
    args = parser.parse_args(argv)

    server = SynapseMcpServer(AgentRole(args.role), args.job_id)
    server.run_stdio()


if __name__ == "__main__":
    main()

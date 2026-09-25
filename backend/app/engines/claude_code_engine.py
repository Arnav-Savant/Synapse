"""Async subprocess wrapper around headless `claude -p`, scoped by the MCP
tool registry (docs/ARCHITECTURE.md §5.2, extended for the multi-agent MCP
tool-boundary mechanism — see `mcp_server/entrypoint.py`/`mcp_server/server.py`).

Independently mirrors `claude_runner/runner.py`'s spawn/timeout/JSON-parse
structure (same subprocess discipline) — not imported from it, this is new,
separate code, same coexistence pattern Phase 2 used for
`source_repo.py`/`source_record_repo.py`.

MCP wiring (empirically verified against the real installed `claude` CLI,
not assumed from docs — see Task 3.4 assignment notes):
- `--mcp-config <path>` takes a JSON file, `{"mcpServers": {"synapse": {...}}}`.
  Tool names get prefixed by that config key (`synapse`), not anything
  internal to the server: `mcp__synapse__<tool_name>`.
- `--strict-mcp-config` must always accompany `--mcp-config` so other
  MCP servers already globally registered on this machine don't leak in.
- `--tools ""` disables all built-in tools; `--allowedTools` re-adds only
  the named MCP tools — this is what enforces per-role tool boundaries by
  construction.
- `cwd` in the `--mcp-config` JSON is silently ignored by the CLI, which is
  why the config built here doesn't set it (`mcp_server/entrypoint.py`
  self-locates via `__file__` instead).
"""

import asyncio
import json
import logging
import sys
import tempfile
from pathlib import Path

from app.engines.base import AgentEngineError, EngineInvocation, EngineResult
from app.repositories import agent_config_repo

logger = logging.getLogger(__name__)

# backend/app/engines/claude_code_engine.py -> parents[1] is backend/app/
_ENTRYPOINT_PATH = Path(__file__).resolve().parents[1] / "mcp_server" / "entrypoint.py"


class ClaudeCodeEngineError(AgentEngineError):
    """A ClaudeCodeEngine invocation failed to run, or the resolved
    AgentConfig row isn't actually configured for engine='claude_code'."""


class ClaudeCodeEngine:
    """One instance can serve any agent role — role/model/effort are
    resolved per-call from the AgentConfig row, never fixed at
    construction time."""

    def __init__(self, session_factory) -> None:
        """session_factory: an async context manager factory yielding an
        AsyncSession, e.g.
        `contextlib.asynccontextmanager(postgres_connection.get_session)` —
        the same wiring idiom `mcp_server/server.py`'s `SynapseMcpServer`
        already uses for its own `_session_factory`."""
        self._session_factory = session_factory

    async def invoke(self, invocation: EngineInvocation) -> EngineResult:
        async with self._session_factory() as session:
            config = await agent_config_repo.get_agent_config(session, invocation.agent_role)

        if config.engine != "claude_code":
            raise ClaudeCodeEngineError(
                f"agent role {invocation.agent_role!r} is configured for engine "
                f"{config.engine!r}, not 'claude_code'"
            )

        logger.info(
            "invoking claude_code engine: role=%s model=%s effort=%s",
            invocation.agent_role,
            config.model,
            config.effort,
        )

        mcp_config_path: Path | None = None
        try:
            argv = ["claude", "-p", invocation.prompt, "--restricted", "--tools", ""]

            if invocation.tool_names:
                mcp_config_path = self._write_mcp_config(invocation)
                argv += ["--mcp-config", str(mcp_config_path), "--strict-mcp-config", "--allowedTools"]
                argv += [f"mcp__synapse__{name}" for name in invocation.tool_names]

            argv += [
                "--model",
                config.model,
                "--effort",
                config.effort,
                "--permission-mode",
                "acceptEdits",
                "--permission-prompts",
                "none",
                "--output-format",
                "json",
                "--no-session-persistence",
            ]

            process = await asyncio.create_subprocess_exec(
                *argv,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=invocation.timeout_seconds
                )
            except asyncio.TimeoutError as exc:
                process.kill()
                await process.wait()
                logger.error(
                    "claude_code engine invocation timed out after %ss: role=%s",
                    invocation.timeout_seconds,
                    invocation.agent_role,
                )
                raise ClaudeCodeEngineError(
                    f"claude_code invocation timed out after {invocation.timeout_seconds}s"
                ) from exc

            if process.returncode != 0:
                logger.error(
                    "claude_code engine exited with code %s: role=%s",
                    process.returncode,
                    invocation.agent_role,
                )
                raise ClaudeCodeEngineError(
                    f"claude exited with code {process.returncode}: "
                    f"{stderr.decode(errors='replace')[:2000]}"
                )

            try:
                payload = json.loads(stdout)
            except json.JSONDecodeError as exc:
                logger.error("claude_code engine output was not valid JSON: %s", exc)
                raise ClaudeCodeEngineError(f"could not parse claude output as JSON: {exc}") from exc

            result = EngineResult(
                is_error=payload.get("is_error", False),
                result_text=payload.get("result", ""),
                cost_usd=payload.get("total_cost_usd"),
                raw_metadata={
                    "session_id": payload.get("session_id"),
                    "permission_denials": payload.get("permission_denials", []),
                },
            )
            logger.info(
                "claude_code engine invocation finished: role=%s cost_usd=%s is_error=%s",
                invocation.agent_role,
                result.cost_usd,
                result.is_error,
            )
            return result
        finally:
            if mcp_config_path is not None:
                mcp_config_path.unlink(missing_ok=True)

    def _write_mcp_config(self, invocation: EngineInvocation) -> Path:
        config = {
            "mcpServers": {
                "synapse": {
                    "command": sys.executable,
                    "args": [
                        str(_ENTRYPOINT_PATH),
                        "--role",
                        invocation.agent_role,
                        "--job-id",
                        invocation.job_id,
                    ],
                }
            }
        }
        fd, path_str = tempfile.mkstemp(suffix=".json", prefix="synapse-mcp-config-")
        path = Path(path_str)
        with open(fd, "w") as f:
            json.dump(config, f)
        return path

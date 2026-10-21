"""Async subprocess wrapper around headless `claude -p`.

Mirrors `claude_runner/runner.py`'s spawn/timeout/JSON-parse structure.
Agents get no MCP tools; `--tools` carries only the built-in tools a role
may use (web tools for a few roles, none otherwise).
"""

import asyncio
import json
import logging

from app.engines.base import AgentEngineError, EngineInvocation, EngineResult
from app.repositories import agent_config_repo

logger = logging.getLogger(__name__)

class ClaudeCodeEngineError(AgentEngineError):
    """A ClaudeCodeEngine invocation failed to run."""


class ClaudeCodeEngine:
    """One instance can serve any agent role — role/model/effort are
    resolved per-call from the AgentConfig row, never fixed at
    construction time."""

    def __init__(self, session_factory) -> None:
        """session_factory: an async context manager factory yielding an
        AsyncSession, e.g.
        `contextlib.asynccontextmanager(postgres_connection.get_session)`."""
        self._session_factory = session_factory

    async def invoke(self, invocation: EngineInvocation) -> EngineResult:
        async with self._session_factory() as session:
            config = await agent_config_repo.get_agent_config(session, invocation.agent_role)

        logger.info(
            "invoking claude_code engine: role=%s model=%s effort=%s",
            invocation.agent_role,
            config.model,
            config.effort,
        )

        argv = ["claude", "-p", invocation.prompt, "--restricted", "--tools", ",".join(invocation.tool_names)]
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

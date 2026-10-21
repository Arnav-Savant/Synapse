"""Async subprocess wrapper around headless `claude -p`.

CLI behaviour verified against the installed CLI (2.1.306), not assumed:
- `--tools "WebSearch,WebFetch"` takes the list form; `--tools ""` disables
  every built-in tool. Listing a tool is not enough to *run* it: with
  `--permission-prompts none` WebSearch is auto-denied unless it is also
  passed to `--allowedTools`, so both flags carry the same list.
- `--output-format stream-json --verbose` emits one JSON event per line.
  A WebFetch call is an assistant `tool_use` event whose `input.url` is the
  fetched page. A WebSearch call's hits arrive on the following `user`
  event as `tool_use_result.results[].content[].url`. The final event has
  `type == "result"` with `is_error`, `result` and `total_cost_usd`.
- `fetched_urls` is therefore WebFetch targets plus WebSearch hit URLs: the
  URLs the session really retrieved. If the stream cannot be parsed it is
  `None`, and callers fall back to live-link checks only.
- `--restricted` drops the code-running tools; `--no-session-persistence`
  keeps runs from piling up session files.

A process-wide semaphore (`MAX_CLAUDE_PROCESSES`) bounds concurrent
subprocesses to protect the subscription's rate limits.
"""

import asyncio
import json
import logging

from app.core.config import get_server_config
from app.engines.base import AgentEngineError, EngineInvocation, EngineResult
from app.repositories import agent_config_repo

logger = logging.getLogger(__name__)

_semaphore: asyncio.Semaphore | None = None


def _process_slots() -> asyncio.Semaphore:
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(get_server_config().max_claude_processes)
    return _semaphore


class ClaudeCodeEngineError(AgentEngineError):
    """A ClaudeCodeEngine invocation failed to run."""


def _parse_stream(stdout: bytes, web_tools: bool) -> tuple[dict, tuple[str, ...] | None]:
    """Returns (the final `result` event, fetched URLs). Raises ClaudeCodeEngineError if there is no result event."""
    result_event: dict | None = None
    urls: list[str] = []
    parse_ok = True
    for raw in stdout.decode(errors="replace").splitlines():
        if not raw.strip():
            continue
        try:
            event = json.loads(raw)
        except json.JSONDecodeError:
            parse_ok = False
            continue
        kind = event.get("type")
        if kind == "result":
            result_event = event
        elif kind == "assistant":
            for block in (event.get("message") or {}).get("content") or []:
                if isinstance(block, dict) and block.get("type") == "tool_use" and block.get("name") == "WebFetch":
                    url = (block.get("input") or {}).get("url")
                    if url:
                        urls.append(url)
        elif kind == "user":
            results = (event.get("tool_use_result") or {}).get("results") if isinstance(event.get("tool_use_result"), dict) else None
            for group in results or []:
                for hit in (group.get("content") or []) if isinstance(group, dict) else []:
                    if isinstance(hit, dict) and hit.get("url"):
                        urls.append(hit["url"])
    if result_event is None:
        raise ClaudeCodeEngineError("claude produced no result event in its output stream")
    if not web_tools:
        return result_event, ()
    return result_event, tuple(dict.fromkeys(urls)) if parse_ok else None


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

        tools = ",".join(invocation.tools)
        argv = ["claude", "-p", invocation.prompt, "--restricted", "--tools", tools]
        if tools:
            argv += ["--allowedTools", tools]
        argv += [
            "--model", config.model,
            "--effort", config.effort,
            "--permission-mode", "acceptEdits",
            "--permission-prompts", "none",
            "--output-format", "stream-json",
            "--verbose",
            "--no-session-persistence",
        ]

        who = f"{invocation.agent_role} (job {invocation.job_id[:8]})"
        async with _process_slots():
            logger.info("agent %s starting: model=%s effort=%s tools=%s", who, config.model, config.effort, tools or "none")
            process = await asyncio.create_subprocess_exec(
                *argv, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=invocation.timeout_seconds)
            except asyncio.TimeoutError as exc:
                logger.error("agent %s timed out after %ss", who, invocation.timeout_seconds)
                raise ClaudeCodeEngineError(f"claude timed out after {invocation.timeout_seconds}s") from exc
            finally:
                if process.returncode is None:  # timeout or cancellation: never leave the subprocess running
                    process.kill()
                    await process.wait()

        if process.returncode != 0:
            detail = stderr.decode(errors="replace")[:2000]
            logger.error("agent %s: claude exited with code %s: %s", who, process.returncode, detail[:300])
            raise ClaudeCodeEngineError(f"claude exited with code {process.returncode}: {detail}")

        try:
            event, fetched_urls = _parse_stream(stdout, web_tools=bool(invocation.tools))
        except ClaudeCodeEngineError as exc:
            logger.error("agent %s: %s", who, exc)
            raise

        result = EngineResult(
            is_error=bool(event.get("is_error", False)),
            result_text=event.get("result") or "",
            cost_usd=event.get("total_cost_usd"),
            fetched_urls=fetched_urls,
            raw_metadata={"session_id": event.get("session_id"), "permission_denials": event.get("permission_denials", [])},
        )
        if result.raw_metadata["permission_denials"]:
            logger.warning("agent %s: %d tool call(s) were denied", who, len(result.raw_metadata["permission_denials"]))
        logger.info(
            "agent %s finished: cost=$%s%s",
            who,
            f"{result.cost_usd:.4f}" if result.cost_usd is not None else "?",
            " (reported an error)" if result.is_error else "",
        )
        return result

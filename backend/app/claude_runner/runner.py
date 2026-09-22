"""Async subprocess wrapper around headless `claude -p` (docs/ARCHITECTURE.md
§5.2). Flags and output shape were confirmed against a real invocation
during the Phase 2 spike (v2.1.278): exit code 0 on success, JSON stdout
with `is_error`, `subtype`, `result`, `session_id`, `total_cost_usd`,
`permission_denials`. `--restricted` + `--tools` keeps this to
filesystem-only access confined to `repo_path`; `CLAUDE.md` in that repo is
still auto-loaded (that's why `--restricted` is used instead of `--bare`).
"""

import asyncio
import json
from dataclasses import dataclass
from pathlib import Path

READ_WRITE_TOOLS = "Read,Write,Edit,Glob,Grep"
READ_ONLY_TOOLS = "Read,Glob,Grep"

DEFAULT_TIMEOUT_SECONDS = 300


class ClaudeRunnerError(RuntimeError):
    """The `claude` invocation failed to run or produced unparseable output."""


@dataclass(frozen=True)
class ClaudeRunResult:
    is_error: bool
    result_text: str
    session_id: str | None
    total_cost_usd: float | None
    permission_denials: list


async def run_claude(
    repo_path: Path,
    prompt: str,
    *,
    tools: str = READ_WRITE_TOOLS,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
) -> ClaudeRunResult:
    process = await asyncio.create_subprocess_exec(
        "claude",
        "-p",
        prompt,
        "--restricted",
        "--tools",
        tools,
        "--add-dir",
        str(repo_path),
        "--permission-mode",
        "acceptEdits",
        "--permission-prompts",
        "none",
        "--output-format",
        "json",
        "--no-session-persistence",
        cwd=repo_path,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )

    try:
        stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=timeout_seconds)
    except asyncio.TimeoutError as exc:
        process.kill()
        await process.wait()
        raise ClaudeRunnerError(f"claude invocation timed out after {timeout_seconds}s") from exc

    if process.returncode != 0:
        raise ClaudeRunnerError(
            f"claude exited with code {process.returncode}: {stderr.decode(errors='replace')[:2000]}"
        )

    try:
        payload = json.loads(stdout)
    except json.JSONDecodeError as exc:
        raise ClaudeRunnerError(f"could not parse claude output as JSON: {exc}") from exc

    return ClaudeRunResult(
        is_error=payload.get("is_error", False),
        result_text=payload.get("result", ""),
        session_id=payload.get("session_id"),
        total_cost_usd=payload.get("total_cost_usd"),
        permission_denials=payload.get("permission_denials", []),
    )

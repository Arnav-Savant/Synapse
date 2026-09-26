"""Naming agent: suggests a category for a newly saved source, via a
read-only Claude Code call that surveys existing source categories and
reasons about a fit — real reasoning over what's already in the
repository, not a slugify heuristic (replaces `claude_runner/naming.py`,
retired this phase along with the filesystem-era source model; there's no
filename concept under the DB model, just a category string on the
`sources` row).

Unlike `text_agent.py`/`chat_agent.py`, this agent needs no MCP tool
access — the existing-category survey is a plain Postgres read
(`source_record_repo.list_source_categories`) done by the caller and
interpolated into the prompt as text, so the invocation carries
`tool_names=()`.
"""

import json
import logging
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from app.engines.base import EngineInvocation
from app.engines.claude_code_engine import ClaudeCodeEngine
from app.repositories import source_record_repo

logger = logging.getLogger(__name__)


class NamingAgentError(RuntimeError):
    """The naming agent's response could not be parsed into a usable
    category, or the invocation itself failed."""


def build_prompt(categories: list[str], content: str, topic_hint: str | None) -> str:
    existing = ", ".join(categories) if categories else "(none yet — this would be the first source)"
    hint_line = (
        f"The user says this is about: {topic_hint!r}." if topic_hint else "No topic hint was given."
    )

    parts = [
        "You are the Naming agent. Decide which category this new piece of "
        "source material belongs to.",
        f"Existing categories already in use: {existing}",
        hint_line,
        "Reuse an existing category if it's a genuine fit for this content — "
        "don't invent a near-duplicate of one that already exists. Otherwise "
        "propose a new, short, kebab-case category.",
        "Respond with ONLY a single JSON object and nothing else, in exactly "
        'this shape: {"category": "..."}',
        f"--- content to file ---\n{content}",
    ]
    return "\n\n".join(parts)


async def suggest_source_location(
    session: AsyncSession, session_factory, content: str, topic_hint: str | None
) -> str:
    """`session`: used for the existing-category survey
    (`source_record_repo.list_source_categories`). `session_factory`: an
    async context manager factory yielding an `AsyncSession` (same idiom as
    `ClaudeCodeEngine.__init__`), needed separately because `ClaudeCodeEngine`
    resolves its `AgentConfig` row per-call rather than taking an
    already-open session.

    Raises NamingAgentError — never silently returns an empty/default
    category — if the invocation fails or its response can't be parsed.
    """
    categories = await source_record_repo.list_source_categories(session)
    prompt = build_prompt(categories, content, topic_hint)

    engine = ClaudeCodeEngine(session_factory)
    result = await engine.invoke(
        EngineInvocation(
            agent_role="naming",
            job_id=f"naming-{uuid4()}",
            prompt=prompt,
            tool_names=(),
        )
    )
    if result.is_error:
        raise NamingAgentError(result.result_text or "claude reported an error")

    category = parse_category(result.result_text)
    logger.info("naming agent suggested category=%r", category)
    return category


def parse_category(result_text: str) -> str:
    """Extracts the fenced/embedded JSON object from result_text, tolerant
    of prose wrapping — same technique as `agents/text_agent.py`'s
    `parse_output`, applied independently here since this module has no
    shared multi-key output contract to reuse."""
    start = result_text.find("{")
    if start == -1:
        raise NamingAgentError(f"no JSON object found in response: {result_text!r}")

    end = result_text.rfind("}")
    data = None
    while end > start:
        candidate = result_text[start : end + 1]
        try:
            data = json.loads(candidate)
            break
        except json.JSONDecodeError:
            end = result_text.rfind("}", start, end)

    if data is None:
        raise NamingAgentError(f"no parseable JSON object found in response: {result_text!r}")

    if not isinstance(data, dict) or "category" not in data:
        raise NamingAgentError(f"parsed JSON missing required key 'category': {result_text!r}")

    category = str(data["category"]).strip()
    if not category:
        raise NamingAgentError(f"claude returned an empty category: {data!r}")

    return category

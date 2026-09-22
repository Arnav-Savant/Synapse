"""Suggests where a new piece of raw source material should be filed
(category + filename), via a read-only Claude Code call — real reasoning
over the existing repository, not a slugify heuristic. Used whenever the
frontend doesn't supply an explicit category/filename: the user provides
content and, optionally, a topic hint, and the system decides the rest.
"""

import json
from pathlib import Path

from app.claude_runner import runner


class NamingError(RuntimeError):
    """Claude Code's suggested filing location could not be parsed/used."""


def _prompt(content: str, topic_hint: str | None) -> str:
    hint = f" The user says this is about: {topic_hint}." if topic_hint else ""
    return (
        "Decide where this new piece of source material belongs in this "
        "repository, as source/<category>/<filename>.md.\n"
        f"{hint}\n"
        "First check the existing category folders under source/ (Glob for them) "
        "and reuse one if it's a genuine fit for this content — don't invent a "
        "near-duplicate of an existing category name. Otherwise propose a new, "
        "short, kebab-case category.\n"
        "Propose a short, descriptive kebab-case filename (lowercase, hyphenated, "
        "no file extension, no generic placeholder like 'chat-001', no dates) that "
        "reflects what this specific content is actually about.\n\n"
        "Respond with ONLY a single JSON object and nothing else, in exactly this "
        'shape: {"category": "...", "filename": "..."}\n\n'
        f"--- content to file ---\n{content}"
    )


async def suggest_source_location(
    knowledge_repo_path: Path, content: str, topic_hint: str | None = None
) -> tuple[str, str]:
    result = await runner.run_claude(
        knowledge_repo_path, _prompt(content, topic_hint), tools=runner.READ_ONLY_TOOLS
    )
    if result.is_error:
        raise NamingError(result.result_text or "claude reported an error")

    try:
        data = json.loads(_extract_json_object(result.result_text))
        category = str(data["category"]).strip()
        filename = str(data["filename"]).strip()
    except (json.JSONDecodeError, KeyError, TypeError) as exc:
        raise NamingError(f"could not parse a category/filename suggestion: {exc}") from exc

    if not category or not filename:
        raise NamingError(f"claude returned an empty category or filename: {data!r}")

    return category, filename


def _extract_json_object(text: str) -> str:
    # Claude Code sometimes wraps the JSON in prose or a code fence despite
    # being asked not to — take the substring between the first '{' and the
    # last '}' rather than requiring the whole response to be bare JSON.
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise NamingError(f"no JSON object found in response: {text!r}")
    return text[start : end + 1]

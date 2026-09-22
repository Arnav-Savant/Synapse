"""Read-only Claude Code chat engine — the default, no-API-key
implementation of `services/chat_service.ChatEngine`.

Uses the same subprocess mechanism as processing (`runner.run_claude`) but
with `--tools "Read,Glob,Grep"` — no `Write`/`Edit`, so a chat question can
never mutate the knowledge base.
"""

from pathlib import Path

from app.claude_runner import prompts, runner


class ChatEngineError(RuntimeError):
    """The chat engine failed to produce a response."""


async def respond(knowledge_repo_path: Path, message: str, concept_slug: str | None) -> str:
    prompt = prompts.chat_prompt(message, concept_slug)
    result = await runner.run_claude(knowledge_repo_path, prompt, tools=runner.READ_ONLY_TOOLS)
    if result.is_error:
        raise ChatEngineError(result.result_text or "claude reported an error")
    return result.result_text

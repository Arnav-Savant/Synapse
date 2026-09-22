"""Chat orchestration: dispatches to a `ChatEngine` implementation.

Phase 6 has exactly one engine — Claude Code, read-only
(`claude_runner/chat_engine.py`). Phase 7 adds a second (LiteLLM)
implementing the same shape and extends `ask()` to pick between them based
on the active-engine setting, without `api/chat.py` changing at all. The
`ChatEngine` protocol documents that shared shape now, before a second
implementation exists, because that second one is already committed for
next phase — see docs/ARCHITECTURE.md §14.2 on when this pattern earns its
place versus when it wouldn't.
"""

from pathlib import Path
from typing import Protocol

from app.claude_runner import chat_engine as claude_chat_engine


class ChatEngine(Protocol):
    async def respond(self, knowledge_repo_path: Path, message: str, concept_slug: str | None) -> str: ...


async def ask(knowledge_repo_path: Path, message: str, concept_slug: str | None = None) -> str:
    return await claude_chat_engine.respond(knowledge_repo_path, message, concept_slug)

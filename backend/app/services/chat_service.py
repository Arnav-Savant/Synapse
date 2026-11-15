"""Chat sessions for the API: create, list, open, delete and ask (ARCHITECTURE §12.6).

Asking stores the owner's message and a pending assistant message, starts the
turn as a background task in this process and returns at once. A chat has at
most one pending turn.
"""

import asyncio
import contextlib
import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.postgres_connection import postgres_connection
from app.db.models import ChatMessage, ChatSession
from app.engines.factory import build_engine
from app.repositories import chat_repo, domain_repo
from app.schemas.chats import ChatDetailOut, ChatSummaryOut, MessageOut
from app.services.chat_runtime import run_turn

logger = logging.getLogger(__name__)

MAX_MESSAGE_CHARS = 8_000
TITLE_CHARS = 80

_running: set[asyncio.Task] = set()  # keeps the background turns from being garbage-collected


class InvalidChatError(ValueError):
    """The request cannot make or continue a chat: no domains, an unknown domain, or an empty message."""


class ChatBusyError(RuntimeError):
    """The chat is still answering."""


class ChatMessageTooLongError(ValueError):
    """The message is over the length limit."""


def _summary(chat: ChatSession, pending: bool) -> ChatSummaryOut:
    return ChatSummaryOut(
        id=chat.id, title=chat.title, domain_slugs=list(chat.domain_slugs), updated_at=chat.updated_at, pending=pending
    )


def _message(message: ChatMessage) -> MessageOut:
    return MessageOut.model_validate(message, from_attributes=True)


async def create_chat(session: AsyncSession, domain_slugs: list[str]) -> ChatSummaryOut:
    slugs = list(dict.fromkeys(domain_slugs))
    if not slugs:
        raise InvalidChatError("choose at least one vault to chat over")
    for slug in slugs:
        try:
            await domain_repo.get_by_slug(session, slug)
        except domain_repo.DomainNotFoundError as exc:
            raise InvalidChatError(f"there is no vault called {slug!r}") from exc
    return _summary(await chat_repo.create_session(session, title="", domain_slugs=slugs), pending=False)


async def list_chats(session: AsyncSession) -> list[ChatSummaryOut]:
    return [_summary(c, await chat_repo.has_pending(session, c.id)) for c in await chat_repo.list_sessions(session)]


async def get_chat(session: AsyncSession, chat_id: str) -> ChatDetailOut:
    chat = await chat_repo.get_session(session, chat_id)
    messages = await chat_repo.list_messages(session, chat_id)
    summary = _summary(chat, any(m.status == "pending" for m in messages))
    return ChatDetailOut(
        **summary.model_dump(),
        messages=[_message(m) for m in messages],
        total_cost_usd=float(sum(m.cost_usd or 0 for m in messages)),
    )


async def delete_chat(session: AsyncSession, chat_id: str) -> None:
    await chat_repo.get_session(session, chat_id)  # 404 for an unknown chat
    if await chat_repo.has_pending(session, chat_id):
        raise ChatBusyError("this chat is still answering")
    await chat_repo.delete_session(session, chat_id)


def start_turn(message_id: str) -> None:
    task = asyncio.create_task(
        run_turn(contextlib.asynccontextmanager(postgres_connection.get_session), build_engine(), message_id)
    )
    _running.add(task)
    task.add_done_callback(_running.discard)


async def ask(session: AsyncSession, chat_id: str, text: str) -> MessageOut:
    chat = await chat_repo.get_session(session, chat_id)
    if not text.strip():
        raise InvalidChatError("write a question first")
    if len(text) > MAX_MESSAGE_CHARS:
        raise ChatMessageTooLongError(f"messages are limited to {MAX_MESSAGE_CHARS:,} characters")
    if await chat_repo.has_pending(session, chat_id):
        raise ChatBusyError("this chat is still answering")
    if not chat.title:
        await chat_repo.set_title(session, chat_id, text.strip()[:TITLE_CHARS])
    await chat_repo.add_message(session, chat_id, role="owner", text=text, status="sent")
    pending = await chat_repo.add_message(session, chat_id, role="assistant", text="", status="pending")
    await chat_repo.update_message(session, pending.id, step="Thinking")
    start_turn(pending.id)
    return _message(await chat_repo.get_message(session, pending.id))


async def fail_interrupted_turns(session: AsyncSession) -> int:
    """At startup, a message still pending was cut off by a restart."""
    return await chat_repo.fail_pending(session, "interrupted by a restart; ask again")

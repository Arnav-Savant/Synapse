"""Chat repository: async Postgres reads/writes for `chat_sessions`,
`chat_messages` and `chat_evidence`.

Each write commits immediately, as in `job_repo`: a turn runs as a background
task while the frontend polls the chat, so every step change and stored
answer must be visible right away. Deleting a session removes its messages
and evidence through the database's ON DELETE CASCADE.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import ChatEvidence, ChatMessage, ChatSession

logger = logging.getLogger(__name__)


class ChatNotFoundError(LookupError):
    """No chat exists for the given id."""


class ChatMessageNotFoundError(LookupError):
    """No chat message exists for the given id."""


@dataclass(frozen=True)
class EvidenceIn:
    domain_slug: str
    note_id: str | None
    note_title: str
    heading: str
    excerpt: str


async def create_session(session: AsyncSession, *, title: str, domain_slugs: list[str]) -> ChatSession:
    chat = ChatSession(title=title, domain_slugs=list(domain_slugs))
    session.add(chat)
    await session.commit()
    logger.info("chat %s created over %d domains: %s", chat.id[:8], len(domain_slugs), ", ".join(domain_slugs))
    return chat


async def list_sessions(session: AsyncSession) -> list[ChatSession]:
    stmt = select(ChatSession).order_by(ChatSession.updated_at.desc())
    return list((await session.execute(stmt)).scalars().all())


async def get_session(session: AsyncSession, chat_id: str) -> ChatSession:
    chat = await session.get(ChatSession, chat_id)
    if chat is None:
        raise ChatNotFoundError(f"no chat with id {chat_id!r}")
    await session.refresh(chat)  # a long-lived session may hold a stale copy
    return chat


async def delete_session(session: AsyncSession, chat_id: str) -> None:
    await session.execute(delete(ChatSession).where(ChatSession.id == chat_id))
    await session.commit()
    logger.info("chat %s deleted with its messages and evidence", chat_id[:8])


async def set_title(session: AsyncSession, chat_id: str, title: str) -> None:
    chat = await get_session(session, chat_id)
    chat.title = title
    await session.commit()


async def set_summary(session: AsyncSession, chat_id: str, summary: str, summarized_through: int) -> None:
    chat = await get_session(session, chat_id)
    chat.summary = summary
    chat.summarized_through = summarized_through
    await session.commit()


async def add_message(
    session: AsyncSession, chat_id: str, *, role: str, text: str, status: str, kind: str = "answer"
) -> ChatMessage:
    """Positions start at 1 and run without gaps within a chat."""
    chat = await get_session(session, chat_id)
    last = (
        await session.execute(select(func.max(ChatMessage.position)).where(ChatMessage.session_id == chat_id))
    ).scalar_one()
    message = ChatMessage(session_id=chat_id, position=(last or 0) + 1, role=role, kind=kind, text=text, status=status)
    session.add(message)
    chat.updated_at = datetime.now(timezone.utc)
    await session.commit()
    return message


async def list_messages(session: AsyncSession, chat_id: str) -> list[ChatMessage]:
    stmt = select(ChatMessage).where(ChatMessage.session_id == chat_id).order_by(ChatMessage.position)
    return list((await session.execute(stmt)).scalars().all())


async def get_message(session: AsyncSession, message_id: str) -> ChatMessage:
    message = await session.get(ChatMessage, message_id)
    if message is None:
        raise ChatMessageNotFoundError(f"no chat message with id {message_id!r}")
    await session.refresh(message)  # a long-lived session may hold a stale copy
    return message


async def update_message(session: AsyncSession, message_id: str, **fields) -> None:
    message = await get_message(session, message_id)
    for name, value in fields.items():
        if not hasattr(ChatMessage, name):
            raise ValueError(f"chat messages have no field {name!r}")
        setattr(message, name, value)
    await session.commit()


async def has_pending(session: AsyncSession, chat_id: str) -> bool:
    stmt = select(ChatMessage.id).where(ChatMessage.session_id == chat_id, ChatMessage.status == "pending").limit(1)
    return (await session.execute(stmt)).first() is not None


async def fail_pending(session: AsyncSession, reason: str) -> int:
    result = await session.execute(
        update(ChatMessage)
        .where(ChatMessage.status == "pending")
        .values(status="failed", error=reason, step=None, updated_at=datetime.now(timezone.utc))
    )
    await session.commit()
    return result.rowcount


async def add_evidence(
    session: AsyncSession, chat_id: str, message_id: str, items: list[EvidenceIn]
) -> list[ChatEvidence]:
    """Refs continue from the chat's highest, so `[E#]` stays unique across the whole chat."""
    last = (
        await session.execute(select(func.max(ChatEvidence.ref)).where(ChatEvidence.session_id == chat_id))
    ).scalar_one()
    rows = [
        ChatEvidence(
            session_id=chat_id, message_id=message_id, ref=(last or 0) + i,
            domain_slug=item.domain_slug, note_id=item.note_id, note_title=item.note_title,
            heading=item.heading, excerpt=item.excerpt,
        )
        for i, item in enumerate(items, start=1)
    ]
    session.add_all(rows)
    await session.commit()
    return rows


async def list_evidence(session: AsyncSession, chat_id: str) -> list[ChatEvidence]:
    stmt = select(ChatEvidence).where(ChatEvidence.session_id == chat_id).order_by(ChatEvidence.ref)
    return list((await session.execute(stmt)).scalars().all())

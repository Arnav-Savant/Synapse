"""Conversation memory for one chat (ARCHITECTURE §12.5).

Memory never crosses chats. `load_memory` gathers what the orchestrator is given
each turn; `maybe_summarize` folds older messages into the running summary after
an answer is stored, so it never delays one.
"""

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.chat_orchestrator import EvidenceView
from app.agents.chat_summarizer import summarize_chat
from app.db.models import ChatEvidence, ChatMessage
from app.engines.base import AgentEngine
from app.repositories import chat_repo

logger = logging.getLogger(__name__)

RECENT_MESSAGES = 6
SUMMARIZE_OVER = 12
EVIDENCE_TEXT_CHARS = 40_000

_COUNTED = ("sent", "answered")  # pending and failed messages carry no conversation


@dataclass
class Memory:
    summary: str
    recent: list[tuple[str, str]]  # (role, text), oldest first
    evidence: list[EvidenceView]  # in ref order


def _counted(messages: list[ChatMessage]) -> list[ChatMessage]:
    return [m for m in messages if m.status in _COUNTED]


def _view(row: ChatEvidence, excerpt: str | None) -> EvidenceView:
    return EvidenceView(ref=row.ref, domain=row.domain_slug, title=row.note_title, heading=row.heading, excerpt=excerpt)


async def load_memory(session: AsyncSession, chat_id: str, before_position: int) -> Memory:
    chat = await chat_repo.get_session(session, chat_id)
    earlier = [m for m in _counted(await chat_repo.list_messages(session, chat_id)) if m.position < before_position]
    recent = [(m.role, m.text) for m in earlier[-RECENT_MESSAGES:]]

    return Memory(summary=chat.summary, recent=recent, evidence=evidence_views(await chat_repo.list_evidence(session, chat_id)))


def evidence_views(rows: list[ChatEvidence]) -> list[EvidenceView]:
    """Newest excerpts in full until EVIDENCE_TEXT_CHARS is reached, older ones by reference only; in ref order."""
    views: list[EvidenceView] = []
    used = 0
    full = True  # once one excerpt does not fit, every older one is listed by reference only
    for row in sorted(rows, key=lambda r: r.ref, reverse=True):
        if full and used + len(row.excerpt) <= EVIDENCE_TEXT_CHARS:
            used += len(row.excerpt)
            views.append(_view(row, row.excerpt))
        else:
            full = False
            views.append(_view(row, None))
    return sorted(views, key=lambda v: v.ref)


def with_recalled(evidence: list[EvidenceView], rows: list[ChatEvidence], refs: list[int]) -> list[EvidenceView]:
    """The same evidence with the excerpts of `refs` filled in."""
    wanted = set(refs)
    text = {r.ref: r.excerpt for r in rows if r.ref in wanted}
    return [
        EvidenceView(ref=e.ref, domain=e.domain, title=e.title, heading=e.heading, excerpt=text.get(e.ref, e.excerpt))
        for e in evidence
    ]


async def maybe_summarize(session: AsyncSession, engine: AgentEngine, chat_id: str) -> float:
    """Returns the cost of the summarizer call; 0.0 when nothing needed folding."""
    chat = await chat_repo.get_session(session, chat_id)
    counted = _counted(await chat_repo.list_messages(session, chat_id))
    if len(counted) - chat.summarized_through <= SUMMARIZE_OVER:
        return 0.0
    covered_to = len(counted) - RECENT_MESSAGES
    folded = [(m.role, m.text) for m in counted[chat.summarized_through : covered_to]]
    result = await summarize_chat(engine, run_id=chat_id, previous_summary=chat.summary, messages=folded)
    await chat_repo.set_summary(session, chat_id, result.value, covered_to)
    return result.cost_usd

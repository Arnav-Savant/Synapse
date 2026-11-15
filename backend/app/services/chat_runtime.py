"""The chat runtime: the agents' hands (ARCHITECTURE §12.1–§12.8).

It calls an agent, carries out the action or tool call the agent returned, gives
the result back as an observation and calls the agent again. It decides nothing
about relevance or routing. It is read-only: nothing here writes a vault file or
an index row, and agents never supply a path, only a `(domain, title)`.

Logs hold counts, durations and ids, never questions, answers or note text.
"""

import asyncio
import logging
import re
import time
from collections.abc import Callable
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.agents.answer_verifier import verify_answer
from app.agents.chat_orchestrator import (
    Answer,
    AskOwner,
    DelegateNavigator,
    DelegateReaders,
    EvidenceView,
    OrchestratorContext,
    ReaderTask,
    Recall,
    orchestrator_step,
)
from app.agents.navigator import NavigatorFinish, navigator_step
from app.agents.reader import ReaderFinish, reader_step
from app.agents.runner import AgentOutputError
from app.db.models import ChatEvidence, ChatMessage
from app.engines.base import AgentEngine, AgentEngineError
from app.repositories import agent_config_repo, chat_repo, domain_repo
from app.repositories.chat_repo import EvidenceIn
from app.schemas.chat_agents import NoteRef, NoteText, Passage, SearchHit, ToolRecord
from app.services import note_reader
from app.services.chat_memory import Memory, evidence_views, load_memory, maybe_summarize, with_recalled
from app.services.vault_map import build_vault_map
from app.vault.titles import title_key

logger = logging.getLogger(__name__)

_CITATION = re.compile(r"\[E(\d+)\]")

# Fallbacks for the limits that live in the roles' `params` (ARCHITECTURE §12.8, §17).
DEFAULT_MAX_STEPS = 8
DEFAULT_VERIFY_ROUNDS = 2
DEFAULT_BUDGET_USD = 1.0
DEFAULT_SUBAGENT_STEPS = 3
MAX_READER_TASK_CHARS = 120_000
SEARCH_HITS = 20

SessionFactory = Callable[[], AbstractAsyncContextManager[AsyncSession]]


class TurnError(Exception):
    """A turn that cannot go on, with a reason fit to show the owner."""


@dataclass
class _Limits:
    max_steps: int = DEFAULT_MAX_STEPS
    verify_rounds: int = DEFAULT_VERIFY_ROUNDS
    budget_usd: float = DEFAULT_BUDGET_USD
    navigator_steps: int = DEFAULT_SUBAGENT_STEPS
    reader_steps: int = DEFAULT_SUBAGENT_STEPS


@dataclass
class _Turn:
    session: AsyncSession
    engine: AgentEngine
    chat_id: str
    message_id: str
    domains: list[str] = field(default_factory=list)
    limits: _Limits = field(default_factory=_Limits)
    cost: float = 0.0
    actions: int = 0
    lock: asyncio.Lock = field(default_factory=asyncio.Lock)  # one AsyncSession cannot serve parallel readers

    @property
    def tag(self) -> str:
        return f"chat {self.chat_id[:8]}: turn {self.message_id[:8]}"


def _limit(params: dict, key: str, default: float) -> float:
    value = params.get(key)
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and value > 0 else default


async def _params(session: AsyncSession, role: str) -> dict:
    try:
        return dict((await agent_config_repo.get_agent_config(session, role)).params or {})
    except agent_config_repo.AgentConfigNotFoundError:
        return {}


async def _read_limits(session: AsyncSession) -> _Limits:
    orchestrator = await _params(session, "chat_orchestrator")
    navigator = await _params(session, "navigator")
    reader = await _params(session, "reader")
    return _Limits(
        max_steps=int(_limit(orchestrator, "max_steps", DEFAULT_MAX_STEPS)),
        verify_rounds=int(_limit(orchestrator, "max_verify_rounds", DEFAULT_VERIFY_ROUNDS)),
        budget_usd=float(_limit(orchestrator, "budget_usd", DEFAULT_BUDGET_USD)),
        navigator_steps=int(_limit(navigator, "max_steps", DEFAULT_SUBAGENT_STEPS)),
        reader_steps=int(_limit(reader, "max_steps", DEFAULT_SUBAGENT_STEPS)),
    )


async def _prepare(turn: _Turn, message: ChatMessage) -> tuple[str, Memory]:
    """Review Focus 2: domains deleted since the chat began are dropped; none left fails the turn."""
    chat = await chat_repo.get_session(turn.session, turn.chat_id)
    for slug in chat.domain_slugs:
        try:
            await domain_repo.get_by_slug(turn.session, slug)
        except domain_repo.DomainNotFoundError:
            continue
        turn.domains.append(slug)
    if not turn.domains:
        raise TurnError("this chat's vaults no longer exist")
    owner = next((m for m in await chat_repo.list_messages(turn.session, turn.chat_id) if m.position == message.position - 1), None)
    if owner is None or owner.role != "owner":
        raise TurnError("the question this answer belongs to could not be found")
    turn.limits = await _read_limits(turn.session)
    logger.info("%s started (domains %s)", turn.tag, ", ".join(turn.domains))
    return owner.text, await load_memory(turn.session, turn.chat_id, owner.position)


def _log_action(turn: _Turn, agent: str, action: str, detail: str, started: float) -> None:
    logger.info("%s %s %s: %s, %.1fs", turn.tag, agent, action, detail, time.monotonic() - started)


async def _set_step(turn: _Turn, step: str) -> None:
    await chat_repo.update_message(turn.session, turn.message_id, step=step)


# ── navigator ────────────────────────────────────────────────────────────────

def _hits_text(hits: list[SearchHit]) -> str:
    if not hits:
        return "no hits"
    return "\n".join(f"{h.domain} / {h.title}" + (f" § {h.heading}" if h.heading else "") + f": {h.snippet}" for h in hits)


def _picks_text(finish: NavigatorFinish) -> str:
    picks = "\n".join(f"- {p.domain} / {p.title}: {p.reason}" for p in finish.picks) or "the navigator found no relevant notes"
    missing = ", ".join(finish.missing) or "none"
    return f"Picks:\n{picks}\nConcepts no note covers: {missing}"


async def _navigate(turn: _Turn, task: str) -> tuple[str, str]:
    """Returns the observation for the orchestrator and the counts for the log."""
    vault_map = await build_vault_map(turn.session, turn.domains)
    log: list[ToolRecord] = []
    steps = turn.limits.navigator_steps
    for i in range(steps):
        result = await navigator_step(
            turn.engine, run_id=turn.message_id, task=task, vault_map=vault_map, log=log, max_steps=steps
        )
        turn.cost += result.cost_usd
        step = result.value
        if isinstance(step, NavigatorFinish):
            return _picks_text(step), f"{len(step.picks)} pick(s), {len(step.missing)} missing"
        if i == steps - 1:
            break  # the last step must finish, so a search now could not be used
        hits = await note_reader.search_vault(turn.session, turn.domains, step.terms, SEARCH_HITS)
        log.append(ToolRecord("search_vault", {"terms": step.terms}, _hits_text(hits)))
    return "the navigator ran out of steps", "ran out of steps"


# ── readers ──────────────────────────────────────────────────────────────────

async def _fetch_note(turn: _Turn, ref: NoteRef) -> NoteText | None:
    """None when the note is not readable. A domain outside this chat is treated as not found."""
    if ref.domain not in turn.domains:
        return None
    async with turn.lock:
        try:
            return await note_reader.read_note(turn.session, ref.domain, ref.title)
        except note_reader.NoteUnavailableError:
            return None  # Review Focus 1: renamed, moved or deleted since the last rescan


def _chars(notes: list[NoteText]) -> int:
    return sum(len(n.text) for n in notes)


async def _read_more(turn: _Turn, step, notes: list[NoteText]) -> ToolRecord:
    arguments = {"domain": step.domain, "title": step.title}
    if any(n.domain == step.domain and title_key(n.title) == title_key(step.title) for n in notes):
        return ToolRecord("read_note", arguments, "you already have this note")
    note = await _fetch_note(turn, NoteRef(domain=step.domain, title=step.title))
    if note is None:
        return ToolRecord("read_note", arguments, "not found; a rescan may help")
    if _chars(notes) + len(note.text) > MAX_READER_TASK_CHARS:
        return ToolRecord("read_note", arguments, "not added: the notes would exceed the size limit")
    notes.append(note)
    return ToolRecord("read_note", arguments, "added to your notes")


async def _run_reader(turn: _Turn, goal: str, notes: list[NoteText]) -> list[Passage] | None:
    """None when the reader used all its steps without finishing."""
    log: list[ToolRecord] = []
    steps = turn.limits.reader_steps
    for _ in range(steps):
        result = await reader_step(
            turn.engine, run_id=turn.message_id, goal=goal, notes=notes, log=log, max_steps=steps
        )
        turn.cost += result.cost_usd
        if isinstance(result.value, ReaderFinish):
            return result.value.passages
        log.append(await _read_more(turn, result.value, notes))
    return None


async def _gather_readers(turn: _Turn, jobs: list[tuple[str, list[NoteText]]]) -> list[list[Passage] | None]:
    tasks = [asyncio.create_task(_run_reader(turn, goal, notes)) for goal, notes in jobs]
    try:
        return await asyncio.gather(*tasks)
    except BaseException:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        raise


async def _load_task_notes(turn: _Turn, task: ReaderTask, label: str, lines: list[str]) -> list[NoteText]:
    notes: list[NoteText] = []
    for ref in task.notes:
        note = await _fetch_note(turn, ref)
        if note is None:
            lines.append(f"{ref.title} ({ref.domain}): not found; a rescan may help")
        elif not any(n.note_id == note.note_id for n in notes):
            notes.append(note)
    if _chars(notes) > MAX_READER_TASK_CHARS:
        lines.append(
            f"{label} refused: its notes total {_chars(notes):,} characters, over the {MAX_READER_TASK_CHARS:,} limit; "
            "split it into smaller tasks"
        )
        return []
    if not notes:
        lines.append(f"{label} not run: none of its notes could be read")
    return notes


async def _read(turn: _Turn, tasks: list[ReaderTask]) -> tuple[str, str]:
    lines: list[str] = []
    jobs: list[tuple[str, list[NoteText]]] = []
    for i, task in enumerate(tasks, 1):
        notes = await _load_task_notes(turn, task, f"task {i}", lines)
        if notes:
            jobs.append((task.goal, notes))
    results = await _gather_readers(turn, jobs) if jobs else []

    items: list[EvidenceIn] = []
    for (goal, notes), passages in zip(jobs, results):
        if passages is None:
            lines.append(f"a reader ran out of steps without finishing (goal: {goal})")
            continue
        by_key = {(n.domain, title_key(n.title)): n for n in notes}
        for p in passages:
            note = by_key[(p.domain, title_key(p.title))]  # the reader's checks guarantee it is there
            items.append(EvidenceIn(note.domain, note.note_id, note.title, p.heading, p.excerpt))
    if items:
        rows = await chat_repo.add_evidence(turn.session, turn.chat_id, turn.message_id, items)
        lines.append("New evidence:")
        lines += [f"E{r.ref}: {r.note_title}" + (f" › {r.heading}" if r.heading else "") for r in rows]
    else:
        lines.append("the readers found no relevant passages")
    return "\n".join(lines), f"{len(jobs)} reader(s), {len(items)} passage(s)"


# ── answers ──────────────────────────────────────────────────────────────────

def _issue_key(issues: list[str]) -> frozenset[str]:
    return frozenset(" ".join(i.split()).casefold() for i in issues)


async def _store(
    turn: _Turn, rows: list[ChatEvidence], *, kind: str, text: str, gaps: list[str], flags: list[str]
) -> None:
    by_ref = {r.ref: r for r in rows}
    citations: list[dict] = []
    for ref in dict.fromkeys(int(n) for n in _CITATION.findall(text)):  # first use, in order, once each
        row = by_ref.get(ref)
        if row is not None:
            citations.append({"ref": ref, "domain": row.domain_slug, "title": row.note_title, "heading": row.heading})
    await chat_repo.update_message(
        turn.session, turn.message_id,
        kind=kind, text=text, citations=citations, gaps=gaps, flags=flags,
        status="answered", step=None, cost_usd=turn.cost,
    )


async def _summarize(turn: _Turn) -> None:
    """After the owner already has the answer; a failure never changes it."""
    try:
        cost = await maybe_summarize(turn.session, turn.engine, turn.chat_id)
        if cost:
            turn.cost += cost
            await chat_repo.update_message(turn.session, turn.message_id, cost_usd=turn.cost)
    except Exception as exc:
        logger.warning("%s: refreshing the chat summary failed (%s); the answer is unaffected", turn.tag, exc)


async def _orchestrate(turn: _Turn, question: str, memory: Memory) -> str:
    """Runs the loop to its end and returns how the turn ended."""
    limits = turn.limits
    ctx = OrchestratorContext(
        domains=turn.domains, summary=memory.summary, recent=memory.recent, evidence=memory.evidence,
        question=question, log=[], steps_left=limits.max_steps, verifier_issues=[],
    )
    rows = await chat_repo.list_evidence(turn.session, turn.chat_id)
    recalled: set[int] = set()
    rounds_used = 0
    last_issues: frozenset[str] | None = None

    while True:
        # Review Focus 4: when the steps or the budget run out, one more call may only answer or ask.
        final = turn.actions >= limits.max_steps or turn.cost >= limits.budget_usd
        ctx.steps_left = max(0, limits.max_steps - turn.actions)
        started = time.monotonic()
        await _set_step(turn, "Thinking")
        result = await orchestrator_step(turn.engine, run_id=turn.message_id, ctx=ctx, final=final)
        turn.cost += result.cost_usd
        turn.actions += 1
        step = result.value

        if isinstance(step, AskOwner):
            await _store(turn, rows, kind="question", text=step.question, gaps=[], flags=[])
            _log_action(turn, "orchestrator", step.action, "asked the owner", started)
            return "asked a question"

        if isinstance(step, Answer):
            await _set_step(turn, "Checking the answer")
            cited = {int(n) for n in _CITATION.findall(step.text)}
            evidence = [EvidenceView(r.ref, r.domain_slug, r.note_title, r.heading, r.excerpt) for r in rows if r.ref in cited]
            verdict = await verify_answer(
                turn.engine, run_id=turn.message_id, question=question, answer_text=step.text, evidence=evidence
            )
            turn.cost += verdict.cost_usd
            issues = verdict.value.issues
            _log_action(turn, "orchestrator", step.action, f"verifier said {verdict.value.verdict}, {len(issues)} issue(s)", started)
            if verdict.value.verdict == "pass":
                await _store(turn, rows, kind="answer", text=step.text, gaps=step.gaps, flags=[])
                return "answered"
            key = _issue_key(issues)
            if rounds_used < limits.verify_rounds and key != last_issues:
                rounds_used += 1
                last_issues = key
                ctx.verifier_issues = issues
                ctx.log.append(ToolRecord("answer", {"gaps": step.gaps}, "the verifier asked for a revision; see the reasons below"))
                continue
            await _store(turn, rows, kind="answer", text=step.text, gaps=step.gaps, flags=issues)  # shown with its flags
            return "answered"

        if isinstance(step, DelegateNavigator):
            await _set_step(turn, "Finding notes")
            observation, detail = await _navigate(turn, step.task)
        elif isinstance(step, DelegateReaders):
            await _set_step(turn, "Reading notes")
            observation, detail = await _read(turn, step.tasks)
            rows = await chat_repo.list_evidence(turn.session, turn.chat_id)
        else:
            assert isinstance(step, Recall)
            recalled.update(step.refs)
            observation, detail = "recalled " + ", ".join(f"E{r}" for r in sorted(step.refs)), f"{len(step.refs)} ref(s)"
        ctx.evidence = with_recalled(evidence_views(rows), rows, sorted(recalled))
        ctx.log.append(ToolRecord(step.action, step.model_dump(exclude={"action"}), observation))
        _log_action(turn, "orchestrator", step.action, detail, started)


async def _run_guarded(session: AsyncSession, engine: AgentEngine, message_id: str) -> None:
    message = await chat_repo.get_message(session, message_id)
    turn = _Turn(session=session, engine=engine, chat_id=message.session_id, message_id=message_id)
    try:
        question, memory = await _prepare(turn, message)
        outcome = await _orchestrate(turn, question, memory)
    except TurnError as exc:
        reason = str(exc)
        logger.warning("%s failed: %s", turn.tag, reason)
    except Exception as exc:
        if isinstance(exc, AgentOutputError):
            turn.cost += exc.cost_usd
        logger.exception("chat %s turn %s failed", turn.chat_id[:8], message_id[:8])
        if isinstance(exc, (AgentOutputError, AgentEngineError)):
            reason = "an agent could not produce a usable reply; ask again"
        else:
            reason = "something went wrong while answering; see the backend log"
    else:
        await _summarize(turn)
        logger.info("%s %s in %d action(s), $%.4f", turn.tag, outcome, turn.actions, turn.cost)
        return
    await chat_repo.update_message(session, message_id, status="failed", error=reason, step=None, cost_usd=turn.cost)


async def run_turn(session_factory: SessionFactory, engine: AgentEngine, message_id: str) -> None:
    """Works out one pending assistant message. Never raises."""
    try:
        async with session_factory() as session:
            await _run_guarded(session, engine, message_id)
    except Exception:
        logger.exception("chat turn %s could not run", message_id[:8])

"""Reconcile: bring the `notes` index back in line with what is on disk (spec §14).

The vault files win. The scan runs at startup and on demand:
- a file with no `synapse_id` is the owner's own note: index it and write an id into it;
- a known id at a new path is a move: update the path;
- a changed hash marks the note `user_modified` (Synapse never overwrites it blindly);
- an indexed note whose file is gone gets the delete cleanup (links stripped, children re-attached).
`.obsidian/` and any other dot-folder is never touched.
"""

import logging
import uuid
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Domain, Note
from app.repositories import domain_repo, note_index_repo
from app.services import note_delete_service
from app.services.note_link_index import reindex_note_links
from app.vault.frontmatter import FrontmatterError, split_frontmatter, with_meta
from app.vault.locks import vault_lock
from app.vault.store import VaultWriteError, file_hash, write_note_atomic
from app.vault.titles import title_key

logger = logging.getLogger(__name__)

_MAX_TITLE_COLUMN = 200


@dataclass
class ReconcileReport:
    removed: int = 0
    added: int = 0
    modified: int = 0
    moved: int = 0


@dataclass
class _VaultFile:
    rel_path: str
    text: str
    meta: dict


def _scan_vault(vault: Path) -> list[_VaultFile]:
    files: list[_VaultFile] = []
    for path in sorted(vault.rglob("*.md")):
        rel = path.relative_to(vault)
        if any(part.startswith(".") for part in rel.parts):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            logger.warning("reconcile: skipping unreadable file %s (%s)", rel, exc)
            continue
        try:
            meta, _ = split_frontmatter(text)
        except FrontmatterError as exc:
            logger.warning("reconcile: skipping %s, its frontmatter is not valid YAML (%s)", rel, exc)
            continue
        files.append(_VaultFile(rel.as_posix(), text, meta))
    return files


def _aliases(meta: dict) -> list[str]:
    value = meta.get("aliases") or []
    return [str(a) for a in ([value] if isinstance(value, str) else value)]


def _fields(meta: dict) -> dict:
    return {
        "aliases": _aliases(meta),
        "summary": str(meta.get("summary") or ""),
        "topic_id": str(meta["topic_id"]) if meta.get("topic_id") else None,
        "job_id": str(meta["job_id"]) if meta.get("job_id") else None,
        "is_hub": meta.get("hub") is True,
    }


async def reconcile_domain(session: AsyncSession, domain: Domain) -> ReconcileReport:
    report = ReconcileReport()
    vault = Path(domain.vault_path)
    if not vault.is_dir():
        logger.error("reconcile: vault folder for %r is missing (%s); skipping this domain", domain.slug, vault)
        return report

    async with vault_lock(domain.slug):
        indexed = {n.synapse_id: n for n in await note_index_repo.list_notes(session, domain.id)}
        files = _scan_vault(vault)
        seen_ids: set[str] = set()
        taken_keys = {title_key(n.title) for n in indexed.values()}
        to_reindex: list[tuple[Note, str]] = []

        # A copied file carries the original's id: the file at the indexed path keeps it, copies get new ids.
        paths_by_id: dict[str, list[str]] = {}
        for vf in files:
            if vf.meta.get("synapse_id"):
                paths_by_id.setdefault(str(vf.meta["synapse_id"]), []).append(vf.rel_path)
        id_owner = {
            sid: (indexed[sid].path if sid in indexed and indexed[sid].path in paths else paths[0])
            for sid, paths in paths_by_id.items()
        }

        for vf in files:
            title = Path(vf.rel_path).stem
            sid = str(vf.meta["synapse_id"]) if vf.meta.get("synapse_id") else None
            if sid is not None and id_owner[sid] != vf.rel_path:
                logger.warning("reconcile: %s duplicates the id of another note, giving it a new id", vf.rel_path)
                sid = None
            if len(title) > _MAX_TITLE_COLUMN:
                logger.warning("reconcile: skipping %s, its name is longer than %d characters", vf.rel_path, _MAX_TITLE_COLUMN)
                continue

            if sid is not None and sid in indexed:
                seen_ids.add(sid)
                note = indexed[sid]
                if note.path != vf.rel_path:
                    logger.info("note %r moved: %s -> %s", note.title, note.path, vf.rel_path)
                    note.path = vf.rel_path
                    report.moved += 1
                if title != note.title:
                    taken_keys.discard(title_key(note.title))
                    note.title = title
                    taken_keys.add(title_key(title))
                current = file_hash(vault / vf.rel_path)
                if current != note.content_hash:
                    if not note.user_modified:
                        logger.info("note %r was edited outside Synapse, marked user-modified", note.title)
                        report.modified += 1
                    note.user_modified = True
                    for key, value in _fields(vf.meta).items():
                        setattr(note, key, value)
                    to_reindex.append((note, vf.text))
                continue

            # Not in the index: either a file the owner wrote, or one whose row was lost.
            if title_key(title) in taken_keys:
                logger.warning("reconcile: skipping %s, another note in %r already has that title", vf.rel_path, domain.slug)
                continue
            text, content_hash = vf.text, None
            if sid is None:
                sid = str(uuid.uuid4())
                text = with_meta(vf.text, {"synapse_id": sid, "domain": domain.slug, "created": date.today()})
                try:
                    content_hash = write_note_atomic(vault / vf.rel_path, text)
                except VaultWriteError as exc:
                    logger.error("reconcile: could not give %s an id, leaving it unindexed (%s)", vf.rel_path, exc)
                    continue
            else:
                content_hash = file_hash(vault / vf.rel_path)
            seen_ids.add(sid)
            taken_keys.add(title_key(title))
            note = await note_index_repo.upsert_note(
                session, synapse_id=sid, domain_id=domain.id, title=title, path=vf.rel_path,
                content_hash=content_hash, **_fields(vf.meta),
            )
            to_reindex.append((note, text))
            report.added += 1
            logger.info("note %r added to the index from %s", title, vf.rel_path)

        await session.flush()
        for note, text in to_reindex:
            await reindex_note_links(session, note, text)
        # A file skipped above (unreadable, broken YAML mid-edit) is still there: never treat it as deleted.
        missing = [sid for sid, n in indexed.items() if sid not in seen_ids and not (vault / n.path).exists()]
        await session.commit()

    if missing:
        plan = await note_delete_service.build_delete_plan(session, domain, note_ids=missing)
        await note_delete_service.apply_delete_plan(session, plan)
        report.removed = len(missing)

    logger.info(
        "reconcile of %r finished: %d added, %d modified, %d moved, %d removed",
        domain.slug, report.added, report.modified, report.moved, report.removed,
    )
    return report


async def reconcile_all(session: AsyncSession) -> dict[str, ReconcileReport]:
    """One domain failing never stops the others."""
    reports: dict[str, ReconcileReport] = {}
    for domain in await domain_repo.list_domains(session):
        try:
            reports[domain.slug] = await reconcile_domain(session, domain)
        except Exception:
            await session.rollback()
            logger.exception("reconcile of %r failed; continuing with the other domains", domain.slug)
    return reports

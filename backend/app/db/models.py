import uuid
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean,
    Computed,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import ARRAY, JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


# Single source of truth for the Note.tsv expression; migration 0005 repeats
# it verbatim. `immutable_array_to_string` is a thin IMMUTABLE wrapper
# created by that migration (Postgres' own array_to_string is only STABLE,
# which generated columns reject).
NOTE_TSV_EXPRESSION = (
    "to_tsvector('simple', coalesce(title, '') || ' ' || "
    "coalesce(immutable_array_to_string(aliases, ' '), '') || ' ' || coalesce(summary, ''))"
)


class Domain(Base):
    __tablename__ = "domains"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    name: Mapped[str] = mapped_column(String(100))
    purpose: Mapped[str] = mapped_column(Text, default="")
    vault_path: Mapped[str] = mapped_column(Text)
    profile: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    # Transient, never persisted: set by domain_service.create_domain so the
    # API can tell the owner an existing vault folder was reused.
    folder_existed: bool = False


class AgentConfig(Base):
    __tablename__ = "agent_configs"

    agent_role: Mapped[str] = mapped_column(String(30), primary_key=True)
    model: Mapped[str] = mapped_column(String(60))
    effort: Mapped[str] = mapped_column(String(10))
    params: Mapped[dict] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Job(Base):
    __tablename__ = "jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    input_kind: Mapped[str] = mapped_column(String(10))  # topic | content
    input_text: Mapped[str] = mapped_column(Text)
    domain_choice: Mapped[str] = mapped_column(String(100))  # a domain slug, or "auto"
    resolved_domains: Mapped[list] = mapped_column(JSONB, default=list)
    status: Mapped[str] = mapped_column(String(20), default="queued")
    current_step: Mapped[str | None] = mapped_column(String(30), nullable=True)
    awaiting_owner: Mapped[bool] = mapped_column(Boolean, default=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    total_cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    workflow_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    profile_snapshot: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    classifier_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class StepRun(Base):
    __tablename__ = "step_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    step: Mapped[str] = mapped_column(String(30))
    agent_role: Mapped[str | None] = mapped_column(String(30), nullable=True)
    attempt: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(20))
    cost_usd: Mapped[float] = mapped_column(Numeric(10, 6), default=0)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class OutlineDraft(Base):
    __tablename__ = "outline_drafts"

    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True)
    tree: Mapped[dict] = mapped_column(JSONB)
    feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)


class Note(Base):
    """Derived, rebuildable index of a vault file; the file is the source of truth."""

    __tablename__ = "notes"

    synapse_id: Mapped[str] = mapped_column(String(36), primary_key=True)
    domain_id: Mapped[str] = mapped_column(String(36), ForeignKey("domains.id", ondelete="CASCADE"), index=True)
    title: Mapped[str] = mapped_column(String(200))
    path: Mapped[str] = mapped_column(Text)
    aliases: Mapped[list[str]] = mapped_column(ARRAY(Text), default=list)
    summary: Mapped[str] = mapped_column(Text, default="")
    content_hash: Mapped[str] = mapped_column(String(64))
    topic_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    job_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    user_modified: Mapped[bool] = mapped_column(Boolean, default=False)
    tsv: Mapped[str] = mapped_column(TSVECTOR, Computed(NOTE_TSV_EXPRESSION, persisted=True))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    __table_args__ = (
        Index("ix_notes_tsv", "tsv", postgresql_using="gin"),
        Index("ix_notes_title_trgm", "title", postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"}),
        Index("uq_notes_domain_title_key", "domain_id", text("lower(title)"), unique=True),
    )


class NoteLink(Base):
    __tablename__ = "note_links"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    src_note_id: Mapped[str] = mapped_column(String(36), ForeignKey("notes.synapse_id", ondelete="CASCADE"), index=True)
    dst_note_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("notes.synapse_id", ondelete="SET NULL"), nullable=True, index=True
    )
    dst_title: Mapped[str] = mapped_column(String(200))
    kind: Mapped[str] = mapped_column(String(10))  # parent | related | body


class NoteDraft(Base):
    __tablename__ = "note_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=_uuid)
    job_id: Mapped[str] = mapped_column(String(36), ForeignKey("jobs.id", ondelete="CASCADE"), index=True)
    domain_id: Mapped[str] = mapped_column(String(36), ForeignKey("domains.id", ondelete="CASCADE"))
    node_key: Mapped[str] = mapped_column(String(100))
    title: Mapped[str] = mapped_column(String(200))
    parents: Mapped[list] = mapped_column(JSONB, default=list)
    body_md: Mapped[str] = mapped_column(Text, default="")
    frontmatter: Mapped[dict] = mapped_column(JSONB, default=dict)
    kind: Mapped[str] = mapped_column(String(10), default="new")  # new | merge
    path: Mapped[str | None] = mapped_column(Text, nullable=True)  # relative to the vault folder
    target_note_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    base_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    validator_flags: Mapped[list] = mapped_column(JSONB, default=list)
    dossier: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    stage: Mapped[str] = mapped_column(String(12), default="researched")  # researched|written|validated|stale
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)

    __table_args__ = (UniqueConstraint("job_id", "domain_id", "node_key", name="uq_note_drafts_job_domain_node"),)

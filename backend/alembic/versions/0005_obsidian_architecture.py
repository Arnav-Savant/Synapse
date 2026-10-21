"""obsidian vault architecture: drop v1 tables, create v2 schema

Revision ID: 0005
Revises: 0004
Create Date: 2026-10-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0005"
down_revision: Union[str, Sequence[str], None] = "0004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Must match app.db.models.NOTE_TSV_EXPRESSION.
_TSV_EXPRESSION = (
    "to_tsvector('simple', coalesce(title, '') || ' ' || "
    "coalesce(immutable_array_to_string(aliases, ' '), '') || ' ' || coalesce(summary, ''))"
)


def _ts(name: str, nullable: bool = False) -> sa.Column:
    return sa.Column(name, sa.DateTime(timezone=True), nullable=nullable)


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE OR REPLACE FUNCTION immutable_array_to_string(text[], text) RETURNS text "
        "LANGUAGE sql IMMUTABLE PARALLEL SAFE AS $$ SELECT array_to_string($1, $2) $$"
    )

    for table in ("job_rounds", "concepts", "sources", "jobs", "agent_configs"):
        op.execute(f"DROP TABLE IF EXISTS {table} CASCADE")

    op.create_table(
        "agent_configs",
        sa.Column("agent_role", sa.String(30), primary_key=True),
        sa.Column("model", sa.String(60), nullable=False),
        sa.Column("effort", sa.String(10), nullable=False),
        sa.Column("params", postgresql.JSONB, nullable=False, server_default="{}"),
        _ts("updated_at"),
    )

    op.create_table(
        "domains",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("name", sa.String(100), nullable=False),
        sa.Column("purpose", sa.Text, nullable=False, server_default=""),
        sa.Column("vault_path", sa.Text, nullable=False),
        sa.Column("profile", postgresql.JSONB, nullable=False, server_default="{}"),
        _ts("created_at"),
        _ts("updated_at"),
    )

    op.create_table(
        "jobs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("input_kind", sa.String(10), nullable=False),
        sa.Column("input_text", sa.Text, nullable=False),
        sa.Column("domain_choice", sa.String(100), nullable=False),
        sa.Column("resolved_domains", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("status", sa.String(20), nullable=False, server_default="queued"),
        sa.Column("current_step", sa.String(30)),
        sa.Column("awaiting_owner", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("error", sa.Text),
        sa.Column("total_cost_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        sa.Column("workflow_id", sa.String(100)),
        sa.Column("profile_snapshot", postgresql.JSONB),
        sa.Column("classifier_confidence", sa.Float),
        _ts("created_at"),
        _ts("updated_at"),
    )

    op.create_table(
        "step_runs",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step", sa.String(30), nullable=False),
        sa.Column("agent_role", sa.String(30)),
        sa.Column("attempt", sa.Integer, nullable=False, server_default="1"),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False, server_default="0"),
        _ts("started_at"),
        _ts("finished_at", nullable=True),
        sa.Column("error", sa.Text),
    )
    op.create_index("ix_step_runs_job_id", "step_runs", ["job_id"])

    op.create_table(
        "outline_drafts",
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("tree", postgresql.JSONB, nullable=False),
        sa.Column("feedback", sa.Text),
        _ts("updated_at"),
    )

    op.create_table(
        "notes",
        sa.Column("synapse_id", sa.String(36), primary_key=True),
        sa.Column("domain_id", sa.String(36), sa.ForeignKey("domains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("path", sa.Text, nullable=False),
        sa.Column("aliases", postgresql.ARRAY(sa.Text), nullable=False, server_default="{}"),
        sa.Column("summary", sa.Text, nullable=False, server_default=""),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("topic_id", sa.String(36)),
        sa.Column("job_id", sa.String(36)),
        sa.Column("user_modified", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("tsv", postgresql.TSVECTOR, sa.Computed(_TSV_EXPRESSION, persisted=True)),
        _ts("created_at"),
        _ts("updated_at"),
    )
    op.create_index("ix_notes_domain_id", "notes", ["domain_id"])
    op.create_index("ix_notes_topic_id", "notes", ["topic_id"])
    op.create_index("ix_notes_job_id", "notes", ["job_id"])
    op.create_index("ix_notes_tsv", "notes", ["tsv"], postgresql_using="gin")
    op.create_index(
        "ix_notes_title_trgm", "notes", ["title"], postgresql_using="gin", postgresql_ops={"title": "gin_trgm_ops"}
    )
    op.execute("CREATE UNIQUE INDEX uq_notes_domain_title_key ON notes (domain_id, lower(title))")

    op.create_table(
        "note_links",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("src_note_id", sa.String(36), sa.ForeignKey("notes.synapse_id", ondelete="CASCADE"), nullable=False),
        sa.Column("dst_note_id", sa.String(36), sa.ForeignKey("notes.synapse_id", ondelete="SET NULL")),
        sa.Column("dst_title", sa.String(200), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
    )
    op.create_index("ix_note_links_src_note_id", "note_links", ["src_note_id"])
    op.create_index("ix_note_links_dst_note_id", "note_links", ["dst_note_id"])

    op.create_table(
        "note_drafts",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("job_id", sa.String(36), sa.ForeignKey("jobs.id", ondelete="CASCADE"), nullable=False),
        sa.Column("domain_id", sa.String(36), sa.ForeignKey("domains.id", ondelete="CASCADE"), nullable=False),
        sa.Column("node_key", sa.String(100), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("parents", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("body_md", sa.Text, nullable=False, server_default=""),
        sa.Column("frontmatter", postgresql.JSONB, nullable=False, server_default="{}"),
        sa.Column("kind", sa.String(10), nullable=False, server_default="new"),
        sa.Column("target_note_id", sa.String(36)),
        sa.Column("base_hash", sa.String(64)),
        sa.Column("validator_flags", postgresql.JSONB, nullable=False, server_default="[]"),
        sa.Column("dossier", postgresql.JSONB),
        sa.Column("stage", sa.String(12), nullable=False, server_default="researched"),
        _ts("updated_at"),
        sa.UniqueConstraint("job_id", "domain_id", "node_key", name="uq_note_drafts_job_domain_node"),
    )
    op.create_index("ix_note_drafts_job_id", "note_drafts", ["job_id"])


def downgrade() -> None:
    raise NotImplementedError("0005 drops v1 data; there is no downgrade path")

"""study chat: sessions, messages and the evidence they hold

Revision ID: 0010
Revises: 0009
Create Date: 2026-11-16

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision: str = "0010"
down_revision: Union[str, Sequence[str], None] = "0009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "chat_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("domain_slugs", JSONB, nullable=False),
        sa.Column("summary", sa.Text, nullable=False),
        sa.Column("summarized_through", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "chat_messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("position", sa.Integer, nullable=False),
        sa.Column("role", sa.String(10), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("text", sa.Text, nullable=False),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("step", sa.String(30), nullable=True),
        sa.Column("citations", JSONB, nullable=False),
        sa.Column("gaps", JSONB, nullable=False),
        sa.Column("flags", JSONB, nullable=False),
        sa.Column("error", sa.Text, nullable=True),
        sa.Column("cost_usd", sa.Numeric(10, 6), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "position", name="uq_chat_messages_session_position"),
    )
    op.create_index("ix_chat_messages_session_id", "chat_messages", ["session_id"])
    op.create_table(
        "chat_evidence",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("session_id", sa.String(36), sa.ForeignKey("chat_sessions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("message_id", sa.String(36), sa.ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False),
        sa.Column("ref", sa.Integer, nullable=False),
        sa.Column("domain_slug", sa.String(100), nullable=False),
        sa.Column("note_id", sa.String(36), nullable=True),
        sa.Column("note_title", sa.String(200), nullable=False),
        sa.Column("heading", sa.String(200), nullable=False),
        sa.Column("excerpt", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("session_id", "ref", name="uq_chat_evidence_session_ref"),
    )
    op.create_index("ix_chat_evidence_session_id", "chat_evidence", ["session_id"])


def downgrade() -> None:
    op.drop_index("ix_chat_evidence_session_id", table_name="chat_evidence")
    op.drop_table("chat_evidence")
    op.drop_index("ix_chat_messages_session_id", table_name="chat_messages")
    op.drop_table("chat_messages")
    op.drop_table("chat_sessions")

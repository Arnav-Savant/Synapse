"""note drafts remember their target path

Revision ID: 0006
Revises: 0005
Create Date: 2026-10-22

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0006"
down_revision: Union[str, Sequence[str], None] = "0005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Path relative to the domain's vault folder, e.g. "Isolation levels/Dirty reads.md".
    op.add_column("note_drafts", sa.Column("path", sa.Text, nullable=True))


def downgrade() -> None:
    op.drop_column("note_drafts", "path")

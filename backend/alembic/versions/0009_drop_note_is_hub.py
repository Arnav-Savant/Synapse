"""notes are no longer flagged as hubs

Revision ID: 0009
Revises: 0008
Create Date: 2026-11-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0009"
down_revision: Union[str, Sequence[str], None] = "0008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.drop_column("notes", "is_hub")


def downgrade() -> None:
    op.add_column("notes", sa.Column("is_hub", sa.Boolean, nullable=False, server_default=sa.false()))

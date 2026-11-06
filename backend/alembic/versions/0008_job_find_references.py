"""jobs can skip the reference search

Revision ID: 0008
Revises: 0007
Create Date: 2026-11-05

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0008"
down_revision: Union[str, Sequence[str], None] = "0007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("find_references", sa.Boolean, nullable=False, server_default=sa.true()))


def downgrade() -> None:
    op.drop_column("jobs", "find_references")

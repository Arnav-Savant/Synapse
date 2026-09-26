"""rename critique_json to structured_output_json

Revision ID: 0003
Revises: 0002
Create Date: 2026-09-26 00:30:18.483010

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0003'
down_revision: Union[str, Sequence[str], None] = '0002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.alter_column(
        'job_rounds',
        'critique_json',
        new_column_name='structured_output_json',
        existing_type=sa.JSON(),
        existing_nullable=True,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.alter_column(
        'job_rounds',
        'structured_output_json',
        new_column_name='critique_json',
        existing_type=sa.JSON(),
        existing_nullable=True,
    )

"""create_novelty_history

Revision ID: 940006fc5bfe
Revises:
Create Date: 2026-04-26 16:31:47.209435

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '940006fc5bfe'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create the novelty_history table and index."""
    op.create_table(
        "novelty_history",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("run_date", sa.Date(), nullable=False),
        sa.Column("problem_name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.Text(), nullable=False),
        sa.Column("opportunity_score", sa.Numeric(4, 1), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index(
        "ix_novelty_history_run_date",
        "novelty_history",
        ["run_date"],
    )


def downgrade() -> None:
    """Drop the novelty_history table and its index."""
    op.drop_index("ix_novelty_history_run_date", table_name="novelty_history")
    op.drop_table("novelty_history")

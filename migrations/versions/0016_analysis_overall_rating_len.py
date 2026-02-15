"""Increase analyses overall_rating length

Revision ID: 0016_analysis_overall_rating_len
Revises: 0015_drop_claim_fields
Create Date: 2026-02-15 00:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0016_analysis_overall_rating_len"
down_revision = "0015_drop_claim_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "analyses",
        "overall_rating",
        existing_type=sa.String(length=20),
        type_=sa.String(length=64),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "analyses",
        "overall_rating",
        existing_type=sa.String(length=64),
        type_=sa.String(length=20),
        existing_nullable=True,
    )

"""Increase claims verdict length

Revision ID: 0013_claim_verdict_length
Revises: 0012_drop_youtube_url_unique
Create Date: 2026-02-13 00:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0013_claim_verdict_length"
down_revision = "0012_drop_youtube_url_unique"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "claims",
        "verdict",
        existing_type=sa.String(length=20),
        type_=sa.String(length=64),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "claims",
        "verdict",
        existing_type=sa.String(length=64),
        type_=sa.String(length=20),
        existing_nullable=True,
    )

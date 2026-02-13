"""Expand claims search_query length to text

Revision ID: 0014_claim_search_query_text
Revises: 0013_claim_verdict_length
Create Date: 2026-02-13 00:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0014_claim_search_query_text"
down_revision = "0013_claim_verdict_length"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "claims",
        "search_query",
        existing_type=sa.String(length=500),
        type_=sa.Text(),
        existing_nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        "claims",
        "search_query",
        existing_type=sa.Text(),
        type_=sa.String(length=500),
        existing_nullable=True,
        postgresql_using="left(search_query, 500)",
    )

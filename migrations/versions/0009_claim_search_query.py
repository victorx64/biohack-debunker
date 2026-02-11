"""Replace claim keywords with search_query

Revision ID: 0009_claim_search_query
Revises: 0008_claim_keywords
Create Date: 2026-02-11 00:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0009_claim_search_query"
down_revision = "0008_claim_keywords"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "claims",
        sa.Column("search_query", sa.String(length=500), nullable=True),
    )
    op.drop_column("claims", "keywords")


def downgrade() -> None:
    op.add_column(
        "claims",
        sa.Column("keywords", sa.ARRAY(sa.String(length=200)), nullable=True),
    )
    op.drop_column("claims", "search_query")

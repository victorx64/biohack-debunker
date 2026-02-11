"""Add claim keywords

Revision ID: 0008_claim_keywords
Revises: 0007_openalex_costs
Create Date: 2026-02-11 00:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0008_claim_keywords"
down_revision = "0007_openalex_costs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "claims",
        sa.Column("keywords", sa.ARRAY(sa.String(length=200)), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("claims", "keywords")

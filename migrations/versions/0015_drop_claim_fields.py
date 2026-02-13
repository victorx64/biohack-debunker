"""Drop category, study_type, and evidence_level from claims

Revision ID: 0015_drop_claim_fields
Revises: 0014_claim_search_query_text
Create Date: 2026-02-13 00:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0015_drop_claim_fields"
down_revision = "0014_claim_search_query_text"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_column("claims", "category")
    op.drop_column("claims", "study_type")
    op.drop_column("claims", "evidence_level")


def downgrade() -> None:
    op.add_column(
        "claims",
        sa.Column("evidence_level", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "claims",
        sa.Column("study_type", sa.String(length=40), nullable=True),
    )
    op.add_column(
        "claims",
        sa.Column("category", sa.String(length=50), nullable=True),
    )

"""Add evidence level and study type to claims

Revision ID: 0010_claim_evidence_fields
Revises: 0009_claim_search_query
Create Date: 2026-02-12 00:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0010_claim_evidence_fields"
down_revision = "0009_claim_search_query"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "claims",
        sa.Column("evidence_level", sa.String(length=20), nullable=True),
    )
    op.add_column(
        "claims",
        sa.Column("study_type", sa.String(length=40), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("claims", "study_type")
    op.drop_column("claims", "evidence_level")

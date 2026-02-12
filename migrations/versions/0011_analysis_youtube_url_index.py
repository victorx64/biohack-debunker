"""Add youtube_url index to analyses

Revision ID: 0011_analysis_youtube_url_index
Revises: 0010_claim_evidence_fields
Create Date: 2026-02-12 00:00:00

"""

from alembic import op


revision = "0011_analysis_youtube_url_index"
down_revision = "0010_claim_evidence_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index(
        "idx_analyses_youtube_url",
        "analyses",
        ["youtube_url"],
    )


def downgrade() -> None:
    op.drop_index("idx_analyses_youtube_url", table_name="analyses")

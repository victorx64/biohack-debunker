"""Add publication type to sources

Revision ID: 0004_source_publication_type
Revises: 0003_analysis_costs
Create Date: 2026-02-11 00:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0004_source_publication_type"
down_revision = "0003_analysis_costs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "sources",
        sa.Column("publication_type", sa.String(length=200)),
    )


def downgrade() -> None:
    op.drop_column("sources", "publication_type")

"""Add OpenAlex source metadata

Revision ID: 0006_source_openalex_fields
Revises: 0005_pub_type_array
Create Date: 2026-02-11 00:00:00

"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "0006_source_openalex_fields"
down_revision = "0005_pub_type_array"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("sources", sa.Column("cited_by_count", sa.Integer()))
    op.add_column("sources", sa.Column("fwci", sa.Float()))
    op.add_column("sources", sa.Column("citation_normalized_percentile", sa.Float()))
    op.add_column("sources", sa.Column("primary_source_display_name", sa.String(length=255)))
    op.add_column("sources", sa.Column("primary_source_is_core", sa.Boolean()))
    op.add_column("sources", sa.Column("counts_by_year", postgresql.JSONB()))
    op.add_column(
        "sources",
        sa.Column("institution_display_names", postgresql.ARRAY(sa.String(length=255))),
    )


def downgrade() -> None:
    op.drop_column("sources", "institution_display_names")
    op.drop_column("sources", "counts_by_year")
    op.drop_column("sources", "primary_source_is_core")
    op.drop_column("sources", "primary_source_display_name")
    op.drop_column("sources", "citation_normalized_percentile")
    op.drop_column("sources", "fwci")
    op.drop_column("sources", "cited_by_count")

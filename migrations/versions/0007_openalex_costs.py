"""Add OpenAlex cost metrics

Revision ID: 0007_openalex_costs
Revises: 0006_source_openalex_fields
Create Date: 2026-02-11 00:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0007_openalex_costs"
down_revision = "0006_source_openalex_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "claims",
        sa.Column("openalex_requests", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analyses",
        sa.Column(
            "total_openalex_requests",
            sa.Integer(),
            nullable=False,
            server_default="0",
        ),
    )


def downgrade() -> None:
    op.drop_column("analyses", "total_openalex_requests")
    op.drop_column("claims", "openalex_requests")

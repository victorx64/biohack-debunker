"""Convert publication type to array

Revision ID: 0005_pub_type_array
Revises: 0004_source_publication_type
Create Date: 2026-02-11 00:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0005_pub_type_array"
down_revision = "0004_source_publication_type"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "sources",
        "publication_type",
        type_=sa.ARRAY(sa.String(length=200)),
        postgresql_using=(
            "CASE WHEN publication_type IS NULL "
            "THEN NULL ELSE ARRAY[publication_type] END"
        ),
    )


def downgrade() -> None:
    op.alter_column(
        "sources",
        "publication_type",
        type_=sa.String(length=200),
        postgresql_using="publication_type[1]",
    )

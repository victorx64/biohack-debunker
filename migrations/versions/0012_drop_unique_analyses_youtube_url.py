"""Drop unique youtube_url constraint on analyses

Revision ID: 0012_drop_youtube_url_unique
Revises: 0011_analysis_youtube_url_index
Create Date: 2026-02-12 00:00:00

"""

from alembic import op


revision = "0012_drop_youtube_url_unique"
down_revision = "0011_analysis_youtube_url_index"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_analyses_youtube_url")
    op.execute("DROP INDEX IF EXISTS analyses_youtube_url_key")
    op.execute('ALTER TABLE analyses DROP CONSTRAINT IF EXISTS "uq_analyses_youtube_url"')
    op.execute('ALTER TABLE analyses DROP CONSTRAINT IF EXISTS "analyses_youtube_url_key"')


def downgrade() -> None:
    op.create_index(
        "analyses_youtube_url_key",
        "analyses",
        ["youtube_url"],
        unique=True,
    )

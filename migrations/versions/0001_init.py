"""Initial schema

Revision ID: 0001_init
Revises: 
Create Date: 2026-02-10 00:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0001_init"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.create_table(
        "users",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.String(length=255), unique=True),
        sa.Column("credits", sa.Integer(), server_default="3", nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "analyses",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", sa.UUID(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("youtube_url", sa.String(length=500), nullable=False),
        sa.Column("youtube_video_id", sa.String(length=20), nullable=False, server_default=""),
        sa.Column("video_title", sa.String(length=500)),
        sa.Column("channel_name", sa.String(length=255)),
        sa.Column("video_duration", sa.Integer()),
        sa.Column("thumbnail_url", sa.String(length=500)),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("transcript", sa.Text()),
        sa.Column("summary", sa.Text()),
        sa.Column("overall_rating", sa.String(length=20)),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime()),
        sa.Column("is_public", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending', 'processing', 'completed', 'failed')",
            name="valid_status",
        ),
    )

    op.create_table(
        "claims",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("analysis_id", sa.UUID(), sa.ForeignKey("analyses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("claim_text", sa.Text(), nullable=False),
        sa.Column("timestamp_start", sa.Integer()),
        sa.Column("timestamp_end", sa.Integer()),
        sa.Column("category", sa.String(length=50)),
        sa.Column("verdict", sa.String(length=20)),
        sa.Column("confidence", sa.Float()),
        sa.Column("explanation", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )

    op.create_table(
        "sources",
        sa.Column("id", sa.UUID(), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("claim_id", sa.UUID(), sa.ForeignKey("claims.id", ondelete="CASCADE"), nullable=False),
        sa.Column("title", sa.String(length=500)),
        sa.Column("url", sa.String(length=1000)),
        sa.Column("source_type", sa.String(length=50)),
        sa.Column("publication_date", sa.Date()),
        sa.Column("relevance_score", sa.Float()),
        sa.Column("snippet", sa.Text()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.text("now()"), nullable=False),
    )

    op.create_index("idx_analyses_user_id", "analyses", ["user_id"])
    op.create_index("idx_analyses_status", "analyses", ["status"])
    op.create_index("idx_analyses_created_at", "analyses", ["created_at"], postgresql_using="btree")
    op.create_index(
        "idx_analyses_public_feed",
        "analyses",
        ["is_public", "created_at"],
        unique=False,
        postgresql_where=sa.text("status = 'completed'"),
    )
    op.create_index("idx_claims_analysis_id", "claims", ["analysis_id"])
    op.create_index("idx_sources_claim_id", "sources", ["claim_id"])


def downgrade() -> None:
    op.drop_index("idx_sources_claim_id", table_name="sources")
    op.drop_index("idx_claims_analysis_id", table_name="claims")
    op.drop_index("idx_analyses_public_feed", table_name="analyses")
    op.drop_index("idx_analyses_created_at", table_name="analyses")
    op.drop_index("idx_analyses_status", table_name="analyses")
    op.drop_index("idx_analyses_user_id", table_name="analyses")

    op.drop_table("sources")
    op.drop_table("claims")
    op.drop_table("analyses")
    op.drop_table("users")

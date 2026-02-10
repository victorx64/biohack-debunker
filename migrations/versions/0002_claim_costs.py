"""Add claim cost metrics

Revision ID: 0002_claim_costs
Revises: 0001_init
Create Date: 2026-02-11 00:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0002_claim_costs"
down_revision = "0001_init"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "claims",
        sa.Column("pubmed_requests", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "claims",
        sa.Column("tavily_requests", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "claims",
        sa.Column("llm_prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "claims",
        sa.Column("llm_completion_tokens", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("claims", "llm_completion_tokens")
    op.drop_column("claims", "llm_prompt_tokens")
    op.drop_column("claims", "tavily_requests")
    op.drop_column("claims", "pubmed_requests")

"""Add analysis cost metrics

Revision ID: 0003_analysis_costs
Revises: 0002_claim_costs
Create Date: 2026-02-11 00:00:00

"""

from alembic import op
import sqlalchemy as sa


revision = "0003_analysis_costs"
down_revision = "0002_claim_costs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "analyses",
        sa.Column("total_pubmed_requests", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analyses",
        sa.Column("total_tavily_requests", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analyses",
        sa.Column("total_llm_prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analyses",
        sa.Column("total_llm_completion_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analyses",
        sa.Column("report_llm_prompt_tokens", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "analyses",
        sa.Column("report_llm_completion_tokens", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("analyses", "report_llm_completion_tokens")
    op.drop_column("analyses", "report_llm_prompt_tokens")
    op.drop_column("analyses", "total_llm_completion_tokens")
    op.drop_column("analyses", "total_llm_prompt_tokens")
    op.drop_column("analyses", "total_tavily_requests")
    op.drop_column("analyses", "total_pubmed_requests")

"""add toc review suggestions

Revision ID: b7d9c1e3f4a5
Revises: 44e1cc4fb0f5
Create Date: 2026-03-30 23:45:00.000000

"""

from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "b7d9c1e3f4a5"
down_revision: Union[str, Sequence[str], None] = "44e1cc4fb0f5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table(
        "llm_toc_review_suggestions",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("sha256", sa.String(length=64), nullable=False),
        sa.Column("prompt_id", sa.Integer(), nullable=False),
        sa.Column("toc_is_valid", sa.Boolean(), nullable=False),
        sa.Column("toc_matches_document", sa.Boolean(), nullable=False),
        sa.Column("toc_invalid_reason", sa.Text(), nullable=True),
        sa.Column("preface_page", sa.Integer(), nullable=True),
        sa.Column("preface_label", sa.String(length=256), nullable=True),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("reasoning_summary", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("applied", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=False), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=False), nullable=False),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompts.id"]),
        sa.ForeignKeyConstraint(["sha256"], ["documents.sha256"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("sha256", "prompt_id"),
    )
    op.create_index(
        op.f("ix_llm_toc_review_suggestions_prompt_id"),
        "llm_toc_review_suggestions",
        ["prompt_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_llm_toc_review_suggestions_sha256"),
        "llm_toc_review_suggestions",
        ["sha256"],
        unique=False,
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index(
        op.f("ix_llm_toc_review_suggestions_sha256"),
        table_name="llm_toc_review_suggestions",
    )
    op.drop_index(
        op.f("ix_llm_toc_review_suggestions_prompt_id"),
        table_name="llm_toc_review_suggestions",
    )
    op.drop_table("llm_toc_review_suggestions")

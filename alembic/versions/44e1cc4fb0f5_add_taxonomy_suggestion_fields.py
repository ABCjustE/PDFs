"""add taxonomy suggestion fields

Revision ID: 44e1cc4fb0f5
Revises: 5b8fd10e3c12
Create Date: 2026-03-30 17:20:00.000000

"""

from typing import Sequence
from typing import Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "44e1cc4fb0f5"
down_revision: Union[str, Sequence[str], None] = "5b8fd10e3c12"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.add_column(
        "llm_taxonomy_suggestions",
        sa.Column("suggested_document_type", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "llm_taxonomy_suggestions",
        sa.Column("suggested_new_subcategory", sa.String(length=256), nullable=True),
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column("llm_taxonomy_suggestions", "suggested_new_subcategory")
    op.drop_column("llm_taxonomy_suggestions", "suggested_document_type")

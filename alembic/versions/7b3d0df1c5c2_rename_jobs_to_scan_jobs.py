"""rename jobs to scan_jobs

Revision ID: 7b3d0df1c5c2
Revises: 2a4a9c6be6e1
Create Date: 2026-04-17 12:45:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "7b3d0df1c5c2"
down_revision: Union[str, Sequence[str], None] = "2a4a9c6be6e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.rename_table("jobs", "scan_jobs")


def downgrade() -> None:
    """Downgrade schema."""
    op.rename_table("scan_jobs", "jobs")

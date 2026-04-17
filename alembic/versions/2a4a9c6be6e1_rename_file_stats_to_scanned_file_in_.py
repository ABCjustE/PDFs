"""rename file_stats to scanned_file_in_job

Revision ID: 2a4a9c6be6e1
Revises: 0f719dabebd7
Create Date: 2026-04-17 12:20:00.000000

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "2a4a9c6be6e1"
down_revision: Union[str, Sequence[str], None] = "0f719dabebd7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.drop_index("ix_file_stats_sha256", table_name="file_stats")
    op.rename_table("file_stats", "scanned_file_in_job")
    op.create_index("ix_scanned_file_in_job_sha256", "scanned_file_in_job", ["sha256"])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_index("ix_scanned_file_in_job_sha256", table_name="scanned_file_in_job")
    op.rename_table("scanned_file_in_job", "file_stats")
    op.create_index("ix_file_stats_sha256", "file_stats", ["sha256"])

"""Project schema migration 004 — file ingest error_message."""

from alembic import op
import sqlalchemy as sa

revision = "004_project_file_error_message"
down_revision = "003_project_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "project_files",
        sa.Column("error_message", sa.Text(), nullable=True),
        schema="project",
    )


def downgrade() -> None:
    op.drop_column("project_files", "error_message", schema="project")

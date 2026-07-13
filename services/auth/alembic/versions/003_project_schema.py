"""Project schema migration 003."""

from alembic import op
import sqlalchemy as sa

revision = "003_project_schema"
down_revision = "002_chat_schema"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS project")
    op.create_table(
        "projects",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="project",
    )
    op.create_index("ix_project_projects_user_id", "projects", ["user_id"], schema="project")
    op.create_table(
        "project_files",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("project.projects.id"), nullable=False),
        sa.Column("filename", sa.String(512), nullable=False),
        sa.Column("content_hash", sa.String(64), nullable=False),
        sa.Column("storage_key", sa.String(1024), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="project",
    )
    op.create_table(
        "project_memory",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("project_id", sa.String(36), sa.ForeignKey("project.projects.id"), nullable=False),
        sa.Column("memory_type", sa.String(64), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_chat_id", sa.String(36), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="project",
    )


def downgrade() -> None:
    op.drop_table("project_memory", schema="project")
    op.drop_table("project_files", schema="project")
    op.drop_index("ix_project_projects_user_id", table_name="projects", schema="project")
    op.drop_table("projects", schema="project")
    op.execute("DROP SCHEMA IF EXISTS project")

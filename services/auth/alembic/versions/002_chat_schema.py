"""Chat schema migration 002."""

from alembic import op
import sqlalchemy as sa

revision = "002_chat_schema"
down_revision = "001_initial_auth"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE SCHEMA IF NOT EXISTS chat")
    op.create_table(
        "chats",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("user_id", sa.String(36), nullable=True),
        sa.Column("project_id", sa.String(36), nullable=True),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("compression_pending", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="chat",
    )
    op.create_index("ix_chat_chats_user_id", "chats", ["user_id"], schema="chat")
    op.create_index("ix_chat_chats_project_id", "chats", ["project_id"], schema="chat")
    op.create_table(
        "messages",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("chat_id", sa.String(36), sa.ForeignKey("chat.chats.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("citations_json", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="chat",
    )
    op.create_table(
        "chat_snapshots",
        sa.Column("chat_id", sa.String(36), sa.ForeignKey("chat.chats.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("snapshot_text", sa.Text(), nullable=False, server_default=""),
        sa.Column("snapshot_turn_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        schema="chat",
    )


def downgrade() -> None:
    op.drop_table("chat_snapshots", schema="chat")
    op.drop_table("messages", schema="chat")
    op.drop_index("ix_chat_chats_project_id", table_name="chats", schema="chat")
    op.drop_index("ix_chat_chats_user_id", table_name="chats", schema="chat")
    op.drop_table("chats", schema="chat")
    op.execute("DROP SCHEMA IF EXISTS chat")

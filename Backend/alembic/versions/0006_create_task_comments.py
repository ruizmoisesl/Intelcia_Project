"""create task_comments and task_attachments

Revision ID: 0006
Revises: 0005
Create Date: 2025-02-05
"""
from alembic import op
import sqlalchemy as sa

revision = "0006"
down_revision = "0005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "task_comments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_comments_task", "task_comments", ["task_id"])
    op.create_table(
        "task_attachments",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("comment_id", sa.Integer(), nullable=False),
        sa.Column("stored_name", sa.String(length=100), nullable=False),
        sa.Column("original_name", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=100), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(["comment_id"], ["task_comments.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_attachments_comment", "task_attachments", ["comment_id"])


def downgrade() -> None:
    op.drop_index("ix_task_attachments_comment", table_name="task_attachments")
    op.drop_table("task_attachments")
    op.drop_index("ix_task_comments_task", table_name="task_comments")
    op.drop_table("task_comments")
"""add users.jira_account_id

Revision ID: 0007
Revises: 0006
Create Date: 2025-02-10
"""
from alembic import op
import sqlalchemy as sa

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("jira_account_id", sa.String(length=64), nullable=True))
    op.create_index("ix_users_jira_account_id", "users", ["jira_account_id"])


def downgrade() -> None:
    op.drop_index("ix_users_jira_account_id", table_name="users")
    op.drop_column("users", "jira_account_id")
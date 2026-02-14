"""add message thread archive fields

Revision ID: 035
Revises: 034
"""
from alembic import op
import sqlalchemy as sa

revision = "035"
down_revision = "034"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("message_threads", sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("message_threads", sa.Column("archived_by_user_id", sa.UUID(), nullable=True))
    op.create_index("ix_message_threads_archived_at", "message_threads", ["archived_at"], unique=False)
    op.create_index("ix_message_threads_archived_by_user_id", "message_threads", ["archived_by_user_id"], unique=False)
    op.create_foreign_key(
        "fk_message_threads_archived_by_user_id_users",
        "message_threads",
        "users",
        ["archived_by_user_id"],
        ["id"],
    )


def downgrade() -> None:
    op.drop_constraint("fk_message_threads_archived_by_user_id_users", "message_threads", type_="foreignkey")
    op.drop_index("ix_message_threads_archived_by_user_id", table_name="message_threads")
    op.drop_index("ix_message_threads_archived_at", table_name="message_threads")
    op.drop_column("message_threads", "archived_by_user_id")
    op.drop_column("message_threads", "archived_at")

"""add repair_orders delete/cancel audit columns

Deleting a repair order used to hard-delete the row and everything
attached to it (quote, parts usage, labor, invoice) with no trace of who
did it or when. This adds the actor + timestamp columns needed to make
delete a soft delete (deleted_at already exists via BaseModel) and to
record who cancelled an order and when, so both actions leave a
retrievable audit trail instead of vanishing.

Revision ID: 065
Revises: 064
Create Date: 2026-07-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "065"
down_revision = "064"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "repair_orders",
        sa.Column("deleted_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )
    op.add_column(
        "repair_orders",
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "repair_orders",
        sa.Column("cancelled_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("repair_orders", "cancelled_by_user_id")
    op.drop_column("repair_orders", "cancelled_at")
    op.drop_column("repair_orders", "deleted_by_user_id")

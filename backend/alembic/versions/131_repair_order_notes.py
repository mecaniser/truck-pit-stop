"""Notes on a repair order: appended, attributed, never overwritten.

The first attempt at this was a pair of text columns the panel wrote over, so a
second note erased the first and no note carried an author or a time. A note
that goes with the order all along has to accumulate, and the order already has
a durable place for things that happened to it: repair_order_history_events.

Notes become events there. What is missing is an owner: deleting "your own"
note cannot key off actor_name, because two people can share a display name and
a renamed user would strand their own entries. So the events get an actor_user_id.

Backfilled as NULL for existing rows: nobody may delete a historical part or
status event through the notes path, which is the correct outcome.

Revision ID: 131_repair_order_notes
Revises: 130_repair_order_shop_notes
"""
from alembic import op
import sqlalchemy as sa

revision = "131_repair_order_notes"
down_revision = "130_repair_order_shop_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "repair_order_history_events",
        sa.Column("actor_user_id", sa.dialects.postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_index(
        "ix_repair_order_history_events_actor_user_id",
        "repair_order_history_events",
        ["actor_user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_repair_order_history_events_actor_user_id", table_name="repair_order_history_events")
    op.drop_column("repair_order_history_events", "actor_user_id")

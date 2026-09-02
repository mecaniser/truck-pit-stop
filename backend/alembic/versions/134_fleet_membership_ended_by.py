"""Record who removed a truck from a fleet board.

A membership row already carries `notes`, which now holds the reason a truck
left, but nothing recorded the person. The fleet activity feed shows an actor
for incidents and inspections because those tables reference a user; without
this column the membership rows in that same feed would always read blank.

Nullable by design: the four memberships already ended, and the customer-sync
path that ends memberships as a side effect of a customer change, have no
person to name.

Revision ID: 134_fleet_membership_ended_by
Revises: 133_ro_projection_fleet_member
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision = "134_fleet_membership_ended_by"
down_revision = "133_ro_projection_fleet_member"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "fleet_memberships",
        sa.Column("ended_by_user_id", UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_fleet_memberships_ended_by_user",
        "fleet_memberships",
        "users",
        ["ended_by_user_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "fk_fleet_memberships_ended_by_user", "fleet_memberships", type_="foreignkey"
    )
    op.drop_column("fleet_memberships", "ended_by_user_id")

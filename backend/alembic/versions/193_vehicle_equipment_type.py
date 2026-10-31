"""Classify company equipment without guessing historical types."""
from alembic import op
import sqlalchemy as sa

revision = "193_vehicle_equipment_type"
down_revision = "192_vehicle_issues"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("vehicles", sa.Column("equipment_type", sa.String(20), nullable=False, server_default="unknown"))
    op.create_check_constraint("ck_vehicles_equipment_type", "vehicles", "equipment_type IN ('unknown', 'tractor', 'trailer', 'other')")


def downgrade():
    op.drop_constraint("ck_vehicles_equipment_type", "vehicles", type_="check")
    op.drop_column("vehicles", "equipment_type")

"""Optional Motive fuel economy with its reporting period."""

from alembic import op
import sqlalchemy as sa

revision = "157_fleet_fuel_economy"
down_revision = "156_historical_invoice_export"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("fleet_telemetry_snapshots", sa.Column("fuel_economy_mpg", sa.Float(), nullable=True))
    op.add_column("fleet_telemetry_snapshots", sa.Column("fuel_economy_period", sa.String(20), nullable=True))
    op.create_check_constraint(
        "ck_telemetry_fuel_economy", "fleet_telemetry_snapshots",
        "(fuel_economy_mpg IS NULL AND fuel_economy_period IS NULL) OR "
        "(fuel_economy_mpg IS NOT NULL AND fuel_economy_period IS NOT NULL "
        "AND fuel_economy_mpg >= 0 AND fuel_economy_mpg <= 100 "
        "AND fuel_economy_period = 'last_30_days')",
    )


def downgrade():
    op.drop_constraint("ck_telemetry_fuel_economy", "fleet_telemetry_snapshots", type_="check")
    op.drop_column("fleet_telemetry_snapshots", "fuel_economy_period")
    op.drop_column("fleet_telemetry_snapshots", "fuel_economy_mpg")

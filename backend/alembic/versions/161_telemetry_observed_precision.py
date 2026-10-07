"""Represent source minute location timestamps without inventing seconds."""

import sqlalchemy as sa
from alembic import op

revision = "161_telemetry_observed_precision"
down_revision = "160_fleet_daily_fuel"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "fleet_telemetry_snapshots",
        sa.Column("observed_precision", sa.String(10), nullable=True),
    )
    op.create_check_constraint(
        "ck_telemetry_observed_precision",
        "fleet_telemetry_snapshots",
        "observed_precision IS NULL OR (observed_at IS NOT NULL AND observed_precision IN ('second', 'minute'))",
    )
    op.create_check_constraint(
        "ck_telemetry_minute_aligned",
        "fleet_telemetry_snapshots",
        "observed_precision IS DISTINCT FROM 'minute' OR date_trunc('minute', observed_at) = observed_at",
    )


def downgrade():
    # Erasing precision would misrepresent minute starts as exact observations.
    op.execute(
        "DO $$ BEGIN IF EXISTS (SELECT 1 FROM fleet_telemetry_snapshots WHERE observed_precision = 'minute') THEN RAISE EXCEPTION 'Retain revision 161: minute observations exist'; END IF; END $$"
    )
    op.drop_constraint(
        "ck_telemetry_minute_aligned", "fleet_telemetry_snapshots", type_="check"
    )
    op.drop_constraint(
        "ck_telemetry_observed_precision", "fleet_telemetry_snapshots", type_="check"
    )
    op.drop_column("fleet_telemetry_snapshots", "observed_precision")

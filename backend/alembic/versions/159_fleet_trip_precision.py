"""Preserve source minute precision and audited trip corrections."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "159_fleet_trip_precision"
down_revision = "158_fleet_trips"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("fleet_trip_snapshots", sa.Column("timestamp_precision", sa.String(10), nullable=False, server_default="second"))
    op.drop_constraint("ck_fleet_trip_completed", "fleet_trip_snapshots", type_="check")
    op.drop_constraint("ck_fleet_trip_driving", "fleet_trip_snapshots", type_="check")
    op.create_check_constraint("ck_fleet_trip_completed", "fleet_trip_snapshots", "ended_at > started_at OR (timestamp_precision = 'minute' AND ended_at = started_at AND driving_seconds > 0)")
    op.create_check_constraint("ck_fleet_trip_driving", "fleet_trip_snapshots", "driving_seconds >= 0 AND driving_seconds <= EXTRACT(EPOCH FROM (ended_at - started_at)) + CASE WHEN timestamp_precision = 'minute' THEN 59 ELSE 0 END")
    op.create_check_constraint("ck_fleet_trip_precision", "fleet_trip_snapshots", "timestamp_precision IN ('second', 'minute')")
    op.create_check_constraint("ck_fleet_trip_minute_aligned", "fleet_trip_snapshots", "timestamp_precision <> 'minute' OR (date_trunc('minute', started_at) = started_at AND date_trunc('minute', ended_at) = ended_at)")
    op.create_unique_constraint("uq_fleet_trip_tenant_id", "fleet_trip_snapshots", ["tenant_id", "id"])
    op.create_table("fleet_trip_revisions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("trip_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("old_digest", sa.String(64), nullable=False),
        sa.Column("replacement_digest", sa.String(64), nullable=False),
        sa.Column("old_snapshot", sa.JSON(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("corrected_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("corrected_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "trip_id"], ["fleet_trip_snapshots.tenant_id", "fleet_trip_snapshots.id"]),
        sa.UniqueConstraint("tenant_id", "trip_id", "old_digest", name="uq_fleet_trip_revision_predecessor"),
    )
    op.create_index("ix_fleet_trip_revisions_id", "fleet_trip_revisions", ["id"])


def downgrade():
    # Reverting code does not require schema downgrade. Abort rather than discard
    # minute-precision rows or correction history during an operator downgrade.
    op.execute("DO $$ BEGIN IF EXISTS (SELECT 1 FROM fleet_trip_revisions) OR EXISTS (SELECT 1 FROM fleet_trip_snapshots WHERE timestamp_precision = 'minute') THEN RAISE EXCEPTION 'Retain revision 159: imported minute trips or correction audit exist'; END IF; END $$")
    op.drop_table("fleet_trip_revisions")
    op.drop_constraint("uq_fleet_trip_tenant_id", "fleet_trip_snapshots", type_="unique")
    for name in ("ck_fleet_trip_minute_aligned", "ck_fleet_trip_precision", "ck_fleet_trip_driving", "ck_fleet_trip_completed"):
        op.drop_constraint(name, "fleet_trip_snapshots", type_="check")
    op.create_check_constraint("ck_fleet_trip_completed", "fleet_trip_snapshots", "ended_at > started_at")
    op.create_check_constraint("ck_fleet_trip_driving", "fleet_trip_snapshots", "driving_seconds >= 0 AND driving_seconds <= EXTRACT(EPOCH FROM (ended_at - started_at))")
    op.drop_column("fleet_trip_snapshots", "timestamp_precision")

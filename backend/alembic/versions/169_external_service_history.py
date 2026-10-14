"""Add private outside-shop records without changing shop billing or mileage."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "169_external_service_history"
down_revision = "168_operation_execution"
branch_labels = None
depends_on = None


def _base():
    return [sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True)]


def upgrade():
    op.create_table("external_service_records", *_base(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("original_vehicle_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("provider_name", sa.String(160), nullable=False),
        sa.Column("service_date", sa.Date(), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("odometer", sa.Integer(), nullable=True),
        sa.Column("reference", sa.String(100), nullable=True),
        sa.Column("reported_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_name", sa.String(255), nullable=False),
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("updated_by_name", sa.String(255), nullable=False),
        sa.UniqueConstraint("tenant_id", "id", name="uq_external_service_tenant_id"),
        sa.ForeignKeyConstraint(["tenant_id", "vehicle_id"], ["vehicles.tenant_id", "vehicles.id"], name="fk_external_service_vehicle", ondelete="RESTRICT"),
        sa.CheckConstraint("version >= 1", name="ck_external_service_version"),
        sa.CheckConstraint("odometer IS NULL OR (odometer >= 0 AND odometer <= 99999999)", name="ck_external_service_odometer"),
        sa.CheckConstraint("reported_cost IS NULL OR (reported_cost >= 0 AND reported_cost <= 9999999999.99)", name="ck_external_service_cost"))
    op.create_index("ix_external_service_records_id", "external_service_records", ["id"])
    op.create_index("ix_external_service_vehicle_date", "external_service_records", ["tenant_id", "vehicle_id", "service_date", "id"])
    op.create_table("external_service_events", *_base(),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("record_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("action", sa.String(16), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_name", sa.String(255), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("snapshot", postgresql.JSONB(), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id", "record_id"], ["external_service_records.tenant_id", "external_service_records.id"], name="fk_external_service_event_record", ondelete="RESTRICT"),
        sa.UniqueConstraint("tenant_id", "request_id", name="uq_external_service_request"),
        sa.UniqueConstraint("tenant_id", "record_id", "version", name="uq_external_service_revision"),
        sa.CheckConstraint("version >= 1", name="ck_external_service_event_version"),
        sa.CheckConstraint("action IN ('create','update','void','restore')", name="ck_external_service_action"))
    op.create_index("ix_external_service_events_id", "external_service_events", ["id"])


def downgrade():
    op.drop_table("external_service_events")
    op.drop_table("external_service_records")

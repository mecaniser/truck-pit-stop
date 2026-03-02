"""add price-builder fields and motor cache table

Revision ID: 038
Revises: 037
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "038"
down_revision = "037"
branch_labels = None
depends_on = None


labor_line_type = sa.Enum(
    "flat_service",
    "repair_operation",
    "manual",
    name="laborlinetype",
)


def upgrade() -> None:
    labor_line_type.create(op.get_bind(), checkfirst=True)

    op.add_column(
        "labor",
        sa.Column("line_type", labor_line_type, nullable=False, server_default="manual"),
    )
    op.add_column("labor", sa.Column("provider", sa.String(length=50), nullable=True))
    op.add_column("labor", sa.Column("provider_operation_id", sa.String(length=120), nullable=True))
    op.add_column(
        "labor",
        sa.Column("auto_recalc_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
    )
    op.add_column("labor", sa.Column("source_service_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "fk_labor_source_service_id_services",
        "labor",
        "services",
        ["source_service_id"],
        ["id"],
    )
    op.create_index(op.f("ix_labor_line_type"), "labor", ["line_type"], unique=False)
    op.create_index(op.f("ix_labor_source_service_id"), "labor", ["source_service_id"], unique=False)

    op.add_column("repair_orders", sa.Column("pricing_locked_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("repair_orders", sa.Column("pricing_lock_reason", sa.String(length=64), nullable=True))

    op.create_table(
        "motor_operation_cache",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vehicle_fingerprint", sa.String(length=255), nullable=False),
        sa.Column("operation_key", sa.String(length=255), nullable=False),
        sa.Column("normalized_hours", sa.Numeric(5, 2), nullable=False),
        sa.Column("payload_json", sa.Text(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "vehicle_fingerprint", "operation_key", name="uq_motor_cache_key"),
    )
    op.create_index(op.f("ix_motor_operation_cache_id"), "motor_operation_cache", ["id"], unique=False)
    op.create_index(
        op.f("ix_motor_operation_cache_tenant_id"),
        "motor_operation_cache",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_motor_operation_cache_vehicle_fingerprint"),
        "motor_operation_cache",
        ["vehicle_fingerprint"],
        unique=False,
    )
    op.create_index(
        op.f("ix_motor_operation_cache_operation_key"),
        "motor_operation_cache",
        ["operation_key"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_motor_operation_cache_operation_key"), table_name="motor_operation_cache")
    op.drop_index(op.f("ix_motor_operation_cache_vehicle_fingerprint"), table_name="motor_operation_cache")
    op.drop_index(op.f("ix_motor_operation_cache_tenant_id"), table_name="motor_operation_cache")
    op.drop_index(op.f("ix_motor_operation_cache_id"), table_name="motor_operation_cache")
    op.drop_table("motor_operation_cache")

    op.drop_column("repair_orders", "pricing_lock_reason")
    op.drop_column("repair_orders", "pricing_locked_at")

    op.drop_index(op.f("ix_labor_source_service_id"), table_name="labor")
    op.drop_index(op.f("ix_labor_line_type"), table_name="labor")
    op.drop_constraint("fk_labor_source_service_id_services", "labor", type_="foreignkey")
    op.drop_column("labor", "source_service_id")
    op.drop_column("labor", "auto_recalc_enabled")
    op.drop_column("labor", "provider_operation_id")
    op.drop_column("labor", "provider")
    op.drop_column("labor", "line_type")

    labor_line_type.drop(op.get_bind(), checkfirst=True)

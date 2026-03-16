"""replace motor cache with internal labor operation memory

Revision ID: 039
Revises: 038
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "039"
down_revision = "038"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(sa.text("UPDATE labor SET provider = 'internal_library' WHERE provider = 'motor'"))

    op.create_table(
        "labor_operation_memory",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("vehicle_signature", sa.String(length=255), nullable=False),
        sa.Column("operation_key", sa.String(length=255), nullable=False),
        sa.Column("operation_name", sa.String(length=255), nullable=False),
        sa.Column("operation_description", sa.Text(), nullable=True),
        sa.Column("provider_operation_id", sa.String(length=120), nullable=True),
        sa.Column("source_provider", sa.String(length=50), nullable=False, server_default="internal_memory"),
        sa.Column("normalized_hours", sa.Numeric(5, 2), nullable=False),
        sa.Column("usage_count", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "vehicle_signature", "operation_key", name="uq_labor_operation_memory_key"),
    )
    op.create_index(op.f("ix_labor_operation_memory_id"), "labor_operation_memory", ["id"], unique=False)
    op.create_index(
        op.f("ix_labor_operation_memory_tenant_id"),
        "labor_operation_memory",
        ["tenant_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_labor_operation_memory_vehicle_signature"),
        "labor_operation_memory",
        ["vehicle_signature"],
        unique=False,
    )
    op.create_index(
        op.f("ix_labor_operation_memory_operation_key"),
        "labor_operation_memory",
        ["operation_key"],
        unique=False,
    )
    op.create_index(
        op.f("ix_labor_operation_memory_provider_operation_id"),
        "labor_operation_memory",
        ["provider_operation_id"],
        unique=False,
    )

    op.drop_index(op.f("ix_motor_operation_cache_operation_key"), table_name="motor_operation_cache")
    op.drop_index(op.f("ix_motor_operation_cache_vehicle_fingerprint"), table_name="motor_operation_cache")
    op.drop_index(op.f("ix_motor_operation_cache_tenant_id"), table_name="motor_operation_cache")
    op.drop_index(op.f("ix_motor_operation_cache_id"), table_name="motor_operation_cache")
    op.drop_table("motor_operation_cache")


def downgrade() -> None:
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

    op.drop_index(op.f("ix_labor_operation_memory_provider_operation_id"), table_name="labor_operation_memory")
    op.drop_index(op.f("ix_labor_operation_memory_operation_key"), table_name="labor_operation_memory")
    op.drop_index(op.f("ix_labor_operation_memory_vehicle_signature"), table_name="labor_operation_memory")
    op.drop_index(op.f("ix_labor_operation_memory_tenant_id"), table_name="labor_operation_memory")
    op.drop_index(op.f("ix_labor_operation_memory_id"), table_name="labor_operation_memory")
    op.drop_table("labor_operation_memory")
    op.execute(
        sa.text(
            "UPDATE labor SET provider = 'motor' WHERE provider IN ('internal_library', 'internal_memory')"
        )
    )

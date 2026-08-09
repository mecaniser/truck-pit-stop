"""add safe vehicle merge audit and source aliases

Revision ID: 110_safe_vehicle_merge
Revises: 109_ets_last_synced_at
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "110_safe_vehicle_merge"
down_revision = "109_ets_last_synced_at"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "vehicle_source_aliases",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("vehicle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vehicles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
        sa.Column("external_id", sa.String(100), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "source", "external_id", name="uq_vehicle_source_alias"),
    )
    op.create_index("ix_vehicle_source_aliases_tenant_id", "vehicle_source_aliases", ["tenant_id"])
    op.create_index("ix_vehicle_source_aliases_vehicle_id", "vehicle_source_aliases", ["vehicle_id"])

    op.create_table(
        "vehicle_merge_records",
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("canonical_vehicle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vehicles.id"), nullable=False),
        sa.Column("duplicate_vehicle_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("vehicles.id"), nullable=False),
        sa.Column("merged_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("merged_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_vehicle_merge_records_tenant_id", "vehicle_merge_records", ["tenant_id"])
    op.create_index("ix_vehicle_merge_records_canonical_vehicle_id", "vehicle_merge_records", ["canonical_vehicle_id"])
    op.create_index("ix_vehicle_merge_records_duplicate_vehicle_id", "vehicle_merge_records", ["duplicate_vehicle_id"])
    op.create_index("ix_vehicle_merge_records_merged_by_user_id", "vehicle_merge_records", ["merged_by_user_id"])
    op.create_index(
        "ix_vehicle_merge_records_tenant_merged_at", "vehicle_merge_records", ["tenant_id", "merged_at"]
    )


def downgrade() -> None:
    op.drop_table("vehicle_merge_records")
    op.drop_table("vehicle_source_aliases")

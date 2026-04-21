"""add service_parts table; make services.base_price nullable

Revision ID: 045
Revises: 044
Create Date: 2026-04-19
"""
from alembic import op
import sqlalchemy as sa


revision = "045"
down_revision = "044"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column("services", "base_price", existing_type=sa.Numeric(10, 2), nullable=True)

    op.add_column(
        "parts_usage",
        sa.Column("source_service_id", sa.UUID(), nullable=True),
    )
    op.create_foreign_key(
        "fk_parts_usage_source_service_id_services",
        "parts_usage",
        "services",
        ["source_service_id"],
        ["id"],
    )
    op.create_index(
        "ix_parts_usage_source_service_id",
        "parts_usage",
        ["source_service_id"],
    )

    op.create_table(
        "service_parts",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("service_id", sa.UUID(), nullable=False),
        sa.Column("inventory_id", sa.UUID(), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["service_id"], ["services.id"]),
        sa.ForeignKeyConstraint(["inventory_id"], ["inventory.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_service_parts_id", "service_parts", ["id"])
    op.create_index("ix_service_parts_tenant_id", "service_parts", ["tenant_id"])
    op.create_index("ix_service_parts_service_id", "service_parts", ["service_id"])
    op.create_index("ix_service_parts_inventory_id", "service_parts", ["inventory_id"])


def downgrade() -> None:
    op.drop_index("ix_service_parts_inventory_id", table_name="service_parts")
    op.drop_index("ix_service_parts_service_id", table_name="service_parts")
    op.drop_index("ix_service_parts_tenant_id", table_name="service_parts")
    op.drop_index("ix_service_parts_id", table_name="service_parts")
    op.drop_table("service_parts")

    op.drop_index("ix_parts_usage_source_service_id", table_name="parts_usage")
    op.drop_constraint(
        "fk_parts_usage_source_service_id_services",
        "parts_usage",
        type_="foreignkey",
    )
    op.drop_column("parts_usage", "source_service_id")

    op.alter_column("services", "base_price", existing_type=sa.Numeric(10, 2), nullable=False)

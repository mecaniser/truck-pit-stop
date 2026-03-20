"""add mileage in/out, po number, sublet labor, recommended services, comeback tracking

Revision ID: 042
Revises: 041
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "042"
down_revision = "041"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # --- repair_orders: mileage in/out, PO number, comeback tracking ---
    op.add_column("repair_orders", sa.Column("mileage_in", sa.Integer(), nullable=True))
    op.add_column("repair_orders", sa.Column("mileage_out", sa.Integer(), nullable=True))
    op.add_column("repair_orders", sa.Column("po_number", sa.String(length=100), nullable=True))
    op.add_column("repair_orders", sa.Column("parent_repair_order_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("repair_orders", sa.Column("is_warranty_repair", sa.Boolean(), nullable=False, server_default=sa.text("false")))
    op.create_foreign_key(
        "fk_repair_orders_parent_ro",
        "repair_orders", "repair_orders",
        ["parent_repair_order_id"], ["id"],
        ondelete="SET NULL",
    )

    # --- inventory: on_order_quantity ---
    op.add_column("inventory", sa.Column("on_order_quantity", sa.Integer(), nullable=False, server_default="0"))

    # --- labor: add SUBLET type + vendor fields ---
    # ALTER TYPE ADD VALUE is safe inside a transaction in PostgreSQL 12+
    op.execute(sa.text("ALTER TYPE laborlinetype ADD VALUE IF NOT EXISTS 'sublet'"))
    op.add_column("labor", sa.Column("vendor_name", sa.String(length=255), nullable=True))
    op.add_column("labor", sa.Column("vendor_cost", sa.Numeric(10, 2), nullable=True))

    # --- recommended_services: new table ---
    op.execute(sa.text("""
        DO $$ BEGIN
            CREATE TYPE recommendedservicepriority AS ENUM ('urgent', 'soon', 'monitor');
        EXCEPTION WHEN duplicate_object THEN null;
        END; $$
    """))
    op.create_table(
        "recommended_services",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repair_order_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("estimated_cost", sa.Numeric(10, 2), nullable=True),
        sa.Column("priority", postgresql.ENUM("urgent", "soon", "monitor", name="recommendedservicepriority", create_type=False), nullable=False, server_default="soon"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_resolved", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("resolved_by_repair_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["repair_order_id"], ["repair_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["resolved_by_repair_order_id"], ["repair_orders.id"],
            name="fk_rec_svc_resolved_by_ro",
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_recommended_services_repair_order_id", "recommended_services", ["repair_order_id"])
    op.create_index("ix_recommended_services_tenant_id", "recommended_services", ["tenant_id"])


def downgrade() -> None:
    op.drop_index("ix_recommended_services_tenant_id", table_name="recommended_services")
    op.drop_index("ix_recommended_services_repair_order_id", table_name="recommended_services")
    op.drop_table("recommended_services")
    op.execute(sa.text("DROP TYPE IF EXISTS recommendedservicepriority"))

    op.drop_column("labor", "vendor_cost")
    op.drop_column("labor", "vendor_name")
    # Note: cannot remove enum values in PostgreSQL; SUBLET stays in laborlinetype

    op.drop_column("inventory", "on_order_quantity")

    op.drop_constraint("fk_repair_orders_parent_ro", "repair_orders", type_="foreignkey")
    op.drop_column("repair_orders", "is_warranty_repair")
    op.drop_column("repair_orders", "parent_repair_order_id")
    op.drop_column("repair_orders", "po_number")
    op.drop_column("repair_orders", "mileage_out")
    op.drop_column("repair_orders", "mileage_in")

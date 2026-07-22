"""separate vehicle identity from accounts and fleet assignment

Revision ID: 099_vehicle_relationships
Revises: 098_merge_repair_invoice_heads
"""

from alembic import op
import sqlalchemy as sa


revision = "099_vehicle_relationships"
down_revision = "098_merge_repair_invoice_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "repair_orders",
        sa.Column("is_fleet_work", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_repair_orders_is_fleet_work", "repair_orders", ["is_fleet_work"])
    op.execute("UPDATE repair_orders SET is_fleet_work = true WHERE is_internal")

    op.add_column(
        "customers",
        sa.Column("fleet_enabled", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_customers_fleet_enabled", "customers", ["fleet_enabled"])

    op.create_table(
        "vehicle_customer_relationships",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("vehicle_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("relationship_type", sa.String(length=32), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "relationship_type IN ('owner', 'operator', 'default_payer')",
            name="ck_vehicle_customer_relationship_type",
        ),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_vehicle_customer_relationships_tenant_id", ["tenant_id"]),
        ("ix_vehicle_customer_relationships_vehicle_id", ["vehicle_id"]),
        ("ix_vehicle_customer_relationships_customer_id", ["customer_id"]),
        ("ix_vehicle_customer_relationships_relationship_type", ["relationship_type"]),
        ("ix_vehicle_customer_relationships_effective_to", ["effective_to"]),
        ("ix_vehicle_customer_relationship_active", ["tenant_id", "customer_id", "relationship_type", "effective_to"]),
    ):
        op.create_index(name, "vehicle_customer_relationships", columns)
    op.create_index(
        "uq_vehicle_customer_relationship_active_role",
        "vehicle_customer_relationships",
        ["vehicle_id", "customer_id", "relationship_type"],
        unique=True,
        postgresql_where=sa.text("effective_to IS NULL AND deleted_at IS NULL"),
    )

    op.create_table(
        "fleet_memberships",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("vehicle_id", sa.UUID(), nullable=False),
        sa.Column("fleet_customer_id", sa.UUID(), nullable=False),
        sa.Column("effective_from", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("effective_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["fleet_customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    for name, columns in (
        ("ix_fleet_memberships_tenant_id", ["tenant_id"]),
        ("ix_fleet_memberships_vehicle_id", ["vehicle_id"]),
        ("ix_fleet_memberships_fleet_customer_id", ["fleet_customer_id"]),
        ("ix_fleet_memberships_effective_to", ["effective_to"]),
        ("ix_fleet_membership_active", ["tenant_id", "fleet_customer_id", "effective_to"]),
    ):
        op.create_index(name, "fleet_memberships", columns)
    op.create_index(
        "uq_fleet_membership_active_vehicle_company",
        "fleet_memberships",
        ["vehicle_id", "fleet_customer_id"],
        unique=True,
        postgresql_where=sa.text("effective_to IS NULL AND deleted_at IS NULL"),
    )

    # Existing customer_id values are preserved as the compatibility/default
    # account and become explicit owner + default-payer relationships. Existing
    # repair_orders are deliberately untouched: their customer_id already is
    # the historical bill-to snapshot for that visit.
    op.execute(
        """
        INSERT INTO vehicle_customer_relationships
          (id, tenant_id, vehicle_id, customer_id, relationship_type, is_primary)
        SELECT gen_random_uuid(), tenant_id, id, customer_id, role, true
        FROM vehicles
        CROSS JOIN (VALUES ('owner'), ('default_payer')) AS roles(role)
        WHERE deleted_at IS NULL
        """
    )
    op.execute(
        """
        UPDATE customers SET fleet_enabled = true
        WHERE is_internal_fleet AND deleted_at IS NULL
        """
    )
    op.execute(
        """
        INSERT INTO fleet_memberships
          (id, tenant_id, vehicle_id, fleet_customer_id)
        SELECT gen_random_uuid(), vehicle.tenant_id, vehicle.id, vehicle.customer_id
        FROM vehicles vehicle
        JOIN customers customer ON customer.id = vehicle.customer_id
        WHERE vehicle.deleted_at IS NULL
          AND customer.deleted_at IS NULL
          AND customer.is_internal_fleet
        """
    )

    # Fast normalized lookup for duplicate detection. It remains non-unique so
    # legacy databases with pre-existing duplicate VINs can migrate safely; new
    # writes are rejected by the API until those legacy collisions are merged.
    op.execute(
        "CREATE INDEX ix_vehicles_tenant_normalized_vin "
        "ON vehicles (tenant_id, upper(vin)) "
        "WHERE vin IS NOT NULL AND length(trim(vin)) = 17 AND deleted_at IS NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ix_vehicles_tenant_normalized_vin")
    for name in (
        "uq_fleet_membership_active_vehicle_company",
        "ix_fleet_membership_active",
        "ix_fleet_memberships_effective_to",
        "ix_fleet_memberships_fleet_customer_id",
        "ix_fleet_memberships_vehicle_id",
        "ix_fleet_memberships_tenant_id",
    ):
        op.drop_index(name, table_name="fleet_memberships")
    op.drop_table("fleet_memberships")
    for name in (
        "uq_vehicle_customer_relationship_active_role",
        "ix_vehicle_customer_relationship_active",
        "ix_vehicle_customer_relationships_effective_to",
        "ix_vehicle_customer_relationships_relationship_type",
        "ix_vehicle_customer_relationships_customer_id",
        "ix_vehicle_customer_relationships_vehicle_id",
        "ix_vehicle_customer_relationships_tenant_id",
    ):
        op.drop_index(name, table_name="vehicle_customer_relationships")
    op.drop_table("vehicle_customer_relationships")
    op.drop_index("ix_customers_fleet_enabled", table_name="customers")
    op.drop_column("customers", "fleet_enabled")
    op.drop_index("ix_repair_orders_is_fleet_work", table_name="repair_orders")
    op.drop_column("repair_orders", "is_fleet_work")

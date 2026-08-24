"""Add purchasing profiles and tenant-owned part supplier sources.

Revision ID: 125_inventory_supplier_sources
Revises: 124_parts_operations_v1
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "125_inventory_supplier_sources"
down_revision = "124_parts_operations_v1"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def upgrade() -> None:
    op.add_column("suppliers", sa.Column("payment_terms", sa.String(100), nullable=True))
    op.add_column("suppliers", sa.Column("default_lead_time_days", sa.Integer(), nullable=True))
    op.add_column("suppliers", sa.Column("minimum_order_amount", sa.Numeric(12, 2), nullable=True))
    op.add_column("suppliers", sa.Column("purchasing_notes", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_supplier_default_lead_time_days",
        "suppliers",
        "default_lead_time_days IS NULL OR (default_lead_time_days >= 0 AND default_lead_time_days <= 365)",
    )
    op.create_check_constraint(
        "ck_supplier_minimum_order_amount",
        "suppliers",
        "minimum_order_amount IS NULL OR minimum_order_amount >= 0",
    )
    op.create_unique_constraint(
        "uq_inventory_tenant_id_id_db038",
        "inventory",
        ["tenant_id", "id"],
    )
    op.create_unique_constraint(
        "uq_suppliers_tenant_id_id_db038",
        "suppliers",
        ["tenant_id", "id"],
    )

    op.create_table(
        "inventory_supplier_sources",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("inventory_id", UUID, sa.ForeignKey("inventory.id"), nullable=False),
        sa.Column("supplier_id", UUID, sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("supplier_part_number", sa.String(150), nullable=True),
        sa.Column("is_preferred", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("minimum_order_quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("pack_quantity", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_unit_cost", sa.Numeric(12, 2), nullable=True),
        sa.Column("lead_time_days", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            name="uq_inventory_supplier_sources_tenant_id_id_db038",
        ),
        sa.UniqueConstraint(
            "tenant_id",
            "id",
            "inventory_id",
            name="uq_inventory_supplier_sources_tenant_id_id_inventory_db038",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "inventory_id"],
            ["inventory.tenant_id", "inventory.id"],
            name="fk_inventory_supplier_sources_tenant_inventory",
        ),
        sa.ForeignKeyConstraint(
            ["tenant_id", "supplier_id"],
            ["suppliers.tenant_id", "suppliers.id"],
            name="fk_inventory_supplier_sources_tenant_supplier",
        ),
        sa.CheckConstraint(
            "minimum_order_quantity >= 1 AND minimum_order_quantity <= 999",
            name="ck_inventory_supplier_source_minimum_quantity",
        ),
        sa.CheckConstraint(
            "pack_quantity >= 1 AND pack_quantity <= 999",
            name="ck_inventory_supplier_source_pack_quantity",
        ),
        sa.CheckConstraint(
            "last_unit_cost IS NULL OR last_unit_cost >= 0",
            name="ck_inventory_supplier_source_last_cost",
        ),
        sa.CheckConstraint(
            "lead_time_days IS NULL OR (lead_time_days >= 0 AND lead_time_days <= 365)",
            name="ck_inventory_supplier_source_lead_time",
        ),
    )
    op.create_index("ix_inventory_supplier_sources_tenant_id", "inventory_supplier_sources", ["tenant_id"])
    op.create_index("ix_inventory_supplier_sources_inventory_id", "inventory_supplier_sources", ["inventory_id"])
    op.create_index("ix_inventory_supplier_sources_supplier_id", "inventory_supplier_sources", ["supplier_id"])
    op.create_index(
        "ux_inventory_supplier_sources_live_pair",
        "inventory_supplier_sources",
        ["tenant_id", "inventory_id", "supplier_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
        sqlite_where=sa.text("deleted_at IS NULL"),
    )
    op.create_index(
        "ux_inventory_supplier_sources_live_preferred",
        "inventory_supplier_sources",
        ["tenant_id", "inventory_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL AND is_preferred"),
        sqlite_where=sa.text("deleted_at IS NULL AND is_preferred = 1"),
    )

    op.add_column(
        "purchase_order_lines",
        sa.Column("supplier_source_id", UUID, nullable=True),
    )
    op.add_column(
        "purchase_order_lines",
        sa.Column("supplier_part_number_snapshot", sa.String(150), nullable=True),
    )
    # The two-column key prevents cross-tenant provenance. The three-column
    # key additionally makes a source usable only with its own inventory item,
    # including writes that bypass the API/service validation layer.
    op.create_foreign_key(
        "fk_po_lines_tenant_supplier_source",
        "purchase_order_lines",
        "inventory_supplier_sources",
        ["tenant_id", "supplier_source_id"],
        ["tenant_id", "id"],
    )
    op.create_foreign_key(
        "fk_po_lines_supplier_source_inventory",
        "purchase_order_lines",
        "inventory_supplier_sources",
        ["tenant_id", "supplier_source_id", "inventory_id"],
        ["tenant_id", "id", "inventory_id"],
    )
    op.create_index(
        "ix_purchase_order_lines_supplier_source_id",
        "purchase_order_lines",
        ["supplier_source_id"],
    )

    # Preserve the existing unambiguous preferred supplier relationship as a
    # usable purchasing source. No fuzzy source or commercial data is inferred.
    op.execute("""
        INSERT INTO inventory_supplier_sources (
            id, tenant_id, inventory_id, supplier_id, is_preferred,
            minimum_order_quantity, pack_quantity, is_active
        )
        SELECT gen_random_uuid(), i.tenant_id, i.id, i.preferred_supplier_id,
               true, 1, 1, true
          FROM inventory i
          JOIN suppliers s
            ON s.id = i.preferred_supplier_id
           AND s.tenant_id = i.tenant_id
           AND s.deleted_at IS NULL
         WHERE i.deleted_at IS NULL
           AND i.preferred_supplier_id IS NOT NULL
           AND s.is_active IS TRUE
    """)

    # Preserve exact purchasing provenance for existing PO lines only when the
    # line's supplier and inventory match the newly backfilled source.
    op.execute("""
        UPDATE purchase_order_lines pol
           SET supplier_source_id = src.id,
               supplier_part_number_snapshot = src.supplier_part_number
          FROM purchase_orders po,
               inventory_supplier_sources src
         WHERE po.id = pol.purchase_order_id
           AND po.tenant_id = pol.tenant_id
           AND src.tenant_id = pol.tenant_id
           AND src.inventory_id = pol.inventory_id
           AND src.supplier_id = po.supplier_id
           AND src.deleted_at IS NULL
           AND pol.deleted_at IS NULL
    """)


def downgrade() -> None:
    op.drop_index("ix_purchase_order_lines_supplier_source_id", table_name="purchase_order_lines")
    op.drop_constraint(
        "fk_po_lines_supplier_source_inventory",
        "purchase_order_lines",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_po_lines_tenant_supplier_source",
        "purchase_order_lines",
        type_="foreignkey",
    )
    op.drop_column("purchase_order_lines", "supplier_part_number_snapshot")
    op.drop_column("purchase_order_lines", "supplier_source_id")
    op.drop_table("inventory_supplier_sources")
    op.drop_constraint("uq_suppliers_tenant_id_id_db038", "suppliers", type_="unique")
    op.drop_constraint("uq_inventory_tenant_id_id_db038", "inventory", type_="unique")
    op.drop_constraint("ck_supplier_minimum_order_amount", "suppliers", type_="check")
    op.drop_constraint("ck_supplier_default_lead_time_days", "suppliers", type_="check")
    op.drop_column("suppliers", "purchasing_notes")
    op.drop_column("suppliers", "minimum_order_amount")
    op.drop_column("suppliers", "default_lead_time_days")
    op.drop_column("suppliers", "payment_terms")

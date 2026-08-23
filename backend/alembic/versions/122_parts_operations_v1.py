"""DB-038 immutable parts operations ledger and purchasing foundation.

Revision ID: 122_parts_operations_v1
Revises: 121_inventory_canonical_sku
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "122_parts_operations_v1"
down_revision = "121_inventory_canonical_sku"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)


def _id_column():
    return sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()"))


def _timestamps(soft_delete=True):
    columns = [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]
    if soft_delete:
        columns.append(sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True))
    return columns


def upgrade() -> None:
    # Refuse an unsafe populated migration rather than inventing balances or
    # catalog ownership. Operators must resolve the listed legacy integrity
    # faults before this immutable ledger can become authoritative.
    op.execute("""
        DO $$ BEGIN
          IF EXISTS (SELECT 1 FROM inventory WHERE stock_quantity < 0 OR cost < 0) THEN
            RAISE EXCEPTION 'DB-038 preflight failed: inventory has negative stock or cost';
          END IF;
          IF EXISTS (
            SELECT 1 FROM parts_usage p LEFT JOIN inventory i ON i.id = p.inventory_id
             WHERE i.id IS NULL
          ) THEN
            RAISE EXCEPTION 'DB-038 preflight failed: orphaned parts usage inventory reference';
          END IF;
          IF EXISTS (
            SELECT 1 FROM inventory WHERE deleted_at IS NULL
             GROUP BY tenant_id, upper(regexp_replace(regexp_replace(sku, '^ETS-', ''), '[^A-Za-z0-9]', '', 'g'))
            HAVING count(*) > 1
          ) THEN
            RAISE EXCEPTION 'DB-038 preflight failed: duplicate canonical inventory SKU';
          END IF;
        END $$;
    """)
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.add_column("tenants", sa.Column("parts_operations_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("suppliers", sa.Column("normalized_name", sa.String(255), nullable=True))
    op.add_column("suppliers", sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("suppliers", sa.Column("account_reference", sa.String(100), nullable=True))
    op.add_column("suppliers", sa.Column("email", sa.String(255), nullable=True))

    op.create_table(
        "inventory_categories",
        _id_column(), sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("name", sa.String(255), nullable=False), sa.Column("normalized_name", sa.String(255), nullable=False),
        sa.Column("description", sa.Text()), sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        *_timestamps(),
    )
    op.create_index("ix_inventory_categories_tenant_id", "inventory_categories", ["tenant_id"])
    op.create_index("ux_inventory_categories_live_name", "inventory_categories", ["tenant_id", "normalized_name"], unique=True, postgresql_where=sa.text("deleted_at IS NULL"))

    # Normalize legacy supplier names only where that produces an unambiguous
    # tenant-local identity. Historical duplicates retain their text name and
    # require an explicit operator merge rather than silently reassigning PO
    # history to a different supplier row.
    op.execute("""
        WITH normalized AS (
          SELECT id, tenant_id, lower(regexp_replace(trim(name), '\\s+', ' ', 'g')) AS normalized_name,
                 count(*) OVER (PARTITION BY tenant_id, lower(regexp_replace(trim(name), '\\s+', ' ', 'g'))) AS name_count
          FROM suppliers WHERE deleted_at IS NULL
        )
        UPDATE suppliers s
           SET normalized_name = CASE WHEN n.name_count = 1 THEN n.normalized_name ELSE NULL END
          FROM normalized n WHERE n.id = s.id
    """)
    op.create_index("ux_suppliers_live_normalized_name", "suppliers", ["tenant_id", "normalized_name"], unique=True, postgresql_where=sa.text("deleted_at IS NULL AND normalized_name IS NOT NULL"))

    op.add_column("inventory", sa.Column("category_id", UUID, sa.ForeignKey("inventory_categories.id"), nullable=True))
    op.add_column("inventory", sa.Column("preferred_supplier_id", UUID, sa.ForeignKey("suppliers.id"), nullable=True))
    op.add_column("inventory", sa.Column("stock_version", sa.BigInteger(), nullable=False, server_default="0"))
    op.create_index("ix_inventory_category_id", "inventory", ["category_id"])
    op.create_index("ix_inventory_preferred_supplier_id", "inventory", ["preferred_supplier_id"])
    # Legacy strings stay intact. Their normalized counterparts are additive,
    # deterministic catalog links used only when the supplier/category match is
    # unambiguous within the owning tenant.
    op.execute("""
        INSERT INTO inventory_categories (id, tenant_id, name, normalized_name, is_active)
        SELECT gen_random_uuid(), tenant_id, min(category), lower(regexp_replace(trim(category), '\\s+', ' ', 'g')), true
        FROM inventory
        WHERE deleted_at IS NULL AND category IS NOT NULL AND trim(category) <> ''
        GROUP BY tenant_id, lower(regexp_replace(trim(category), '\\s+', ' ', 'g'))
    """)
    op.execute("""
        UPDATE inventory i SET category_id = c.id
        FROM inventory_categories c
        WHERE i.tenant_id = c.tenant_id AND i.deleted_at IS NULL
          AND i.category IS NOT NULL
          AND c.normalized_name = lower(regexp_replace(trim(i.category), '\\s+', ' ', 'g'))
    """)
    op.execute("""
        WITH candidates AS (
          SELECT
            i.id AS inventory_id,
            s.id AS supplier_id,
            count(s.id) OVER (PARTITION BY i.id) AS supplier_count
          FROM inventory i LEFT JOIN suppliers s
            ON s.tenant_id = i.tenant_id AND s.deleted_at IS NULL
           AND s.normalized_name = lower(regexp_replace(trim(i.supplier_name), '\\s+', ' ', 'g'))
          WHERE i.deleted_at IS NULL AND i.supplier_name IS NOT NULL AND trim(i.supplier_name) <> ''
        )
        UPDATE inventory i SET preferred_supplier_id = c.supplier_id
        FROM candidates c WHERE i.id = c.inventory_id AND c.supplier_count = 1
    """)

    op.create_table(
        "inventory_movements",
        _id_column(), sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("inventory_id", UUID, sa.ForeignKey("inventory.id"), nullable=False),
        sa.Column("bucket", sa.String(24), nullable=False), sa.Column("movement_type", sa.String(64), nullable=False),
        sa.Column("quantity_delta", sa.Integer(), nullable=False), sa.Column("balance_before", sa.Integer(), nullable=False), sa.Column("balance_after", sa.Integer(), nullable=False),
        sa.Column("unit_cost_snapshot", sa.Numeric(12, 2)), sa.Column("wac_before", sa.Numeric(12, 2)), sa.Column("wac_after", sa.Numeric(12, 2)),
        sa.Column("source_type", sa.String(64)), sa.Column("source_id", UUID), sa.Column("destination_type", sa.String(64)), sa.Column("destination_id", UUID),
        sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id")), sa.Column("actor_display_name_snapshot", sa.String(255)),
        sa.Column("reason_code", sa.String(100)), sa.Column("note", sa.Text()), sa.Column("idempotency_key", sa.String(128)),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")), *_timestamps(False),
        sa.CheckConstraint("quantity_delta <> 0", name="ck_inventory_movement_nonzero"),
        sa.CheckConstraint("balance_before >= 0 AND balance_after >= 0", name="ck_inventory_movement_nonnegative"),
        sa.CheckConstraint("balance_after = balance_before + quantity_delta", name="ck_inventory_movement_balance"),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_inventory_movement_idempotency"),
    )
    op.create_index("ix_inventory_movements_tenant_inventory", "inventory_movements", ["tenant_id", "inventory_id", "occurred_at"])

    op.create_table(
        "purchase_orders", _id_column(), sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("po_number", sa.String(100), nullable=False), sa.Column("supplier_id", UUID, sa.ForeignKey("suppliers.id"), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"), sa.Column("ordered_at", sa.DateTime(timezone=True)), sa.Column("expected_at", sa.DateTime(timezone=True)), sa.Column("notes", sa.Text()), sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id")), sa.Column("submitted_by_user_id", UUID, sa.ForeignKey("users.id")), *_timestamps(),
    )
    op.create_index("ux_purchase_orders_live_number", "purchase_orders", ["tenant_id", "po_number"], unique=True, postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_table(
        "purchase_order_lines", _id_column(), sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("purchase_order_id", UUID, sa.ForeignKey("purchase_orders.id"), nullable=False), sa.Column("inventory_id", UUID, sa.ForeignKey("inventory.id"), nullable=False),
        sa.Column("sku_snapshot", sa.String(100), nullable=False), sa.Column("description_snapshot", sa.String(255), nullable=False), sa.Column("unit_type_snapshot", sa.String(20), nullable=False), sa.Column("unit_cost_snapshot", sa.Numeric(12,2), nullable=False), sa.Column("core_charge_snapshot", sa.Numeric(12,2), nullable=False, server_default="0"),
        sa.Column("ordered_quantity", sa.Integer(), nullable=False), sa.Column("received_quantity", sa.Integer(), nullable=False, server_default="0"), *_timestamps(),
        sa.CheckConstraint("ordered_quantity BETWEEN 1 AND 999", name="ck_po_line_ordered_quantity"), sa.CheckConstraint("received_quantity BETWEEN 0 AND ordered_quantity", name="ck_po_line_received_quantity"),
    )
    op.create_index("ix_purchase_order_lines_tenant_po", "purchase_order_lines", ["tenant_id", "purchase_order_id"])

    op.create_table(
        "parts_operation_idempotency", _id_column(), sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("operation_family", sa.String(64), nullable=False), sa.Column("idempotency_key", sa.String(128), nullable=False), sa.Column("request_fingerprint", sa.String(128), nullable=False),
        sa.Column("status_code", sa.Integer()), sa.Column("response_body", sa.Text()), sa.Column("completed_at", sa.DateTime(timezone=True)), *_timestamps(False),
        sa.UniqueConstraint("tenant_id", "operation_family", "idempotency_key", name="uq_parts_operation_idempotency"),
    )
    op.create_table(
        "purchase_receipts", _id_column(), sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False), sa.Column("purchase_order_id", UUID, sa.ForeignKey("purchase_orders.id"), nullable=False), sa.Column("receipt_number", sa.String(100), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False), sa.Column("supplier_reference", sa.String(100)), sa.Column("notes", sa.Text()), sa.Column("received_by_user_id", UUID, sa.ForeignKey("users.id")), sa.Column("operation_family", sa.String(64), nullable=False, server_default="po_receipt"), sa.Column("idempotency_key", sa.String(128), nullable=False), sa.Column("request_fingerprint", sa.String(128), nullable=False), *_timestamps(False),
        sa.UniqueConstraint("tenant_id", "operation_family", "idempotency_key", name="uq_purchase_receipt_idempotency"),
    )
    op.create_table(
        "purchase_receipt_lines", _id_column(), sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False), sa.Column("purchase_receipt_id", UUID, sa.ForeignKey("purchase_receipts.id"), nullable=False), sa.Column("purchase_order_line_id", UUID, sa.ForeignKey("purchase_order_lines.id"), nullable=False), sa.Column("inventory_id", UUID, sa.ForeignKey("inventory.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False), sa.Column("unit_cost", sa.Numeric(12,2), nullable=False), sa.Column("wac_before", sa.Numeric(12,2), nullable=False), sa.Column("wac_after", sa.Numeric(12,2), nullable=False), sa.Column("balance_before", sa.Integer(), nullable=False), sa.Column("balance_after", sa.Integer(), nullable=False), *_timestamps(False),
    )

    op.create_table(
        "core_obligations", _id_column(), sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False), sa.Column("parts_usage_id", UUID, sa.ForeignKey("parts_usage.id"), nullable=False), sa.Column("inventory_id", UUID, sa.ForeignKey("inventory.id"), nullable=False), sa.Column("supplier_id", UUID, sa.ForeignKey("suppliers.id")), sa.Column("quantity", sa.Integer(), nullable=False), sa.Column("unit_core_value_snapshot", sa.Numeric(12,2), nullable=False), sa.Column("status", sa.String(24), nullable=False, server_default="expected"), sa.Column("version", sa.Integer(), nullable=False, server_default="1"), sa.Column("reason", sa.Text()), *_timestamps(),
    )
    op.create_index("ux_core_obligations_live_origin", "core_obligations", ["tenant_id", "parts_usage_id"], unique=True, postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_table(
        "vendor_returns", _id_column(), sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False), sa.Column("return_number", sa.String(100), nullable=False), sa.Column("supplier_id", UUID, sa.ForeignKey("suppliers.id"), nullable=False), sa.Column("kind", sa.String(16), nullable=False), sa.Column("status", sa.String(24), nullable=False, server_default="draft"), sa.Column("version", sa.Integer(), nullable=False, server_default="1"), sa.Column("submitted_at", sa.DateTime(timezone=True)), sa.Column("shipped_at", sa.DateTime(timezone=True)), sa.Column("credited_at", sa.DateTime(timezone=True)), sa.Column("supplier_reference", sa.String(100)), sa.Column("notes", sa.Text()), sa.Column("reason", sa.String(100)), sa.Column("reverses_return_id", UUID, sa.ForeignKey("vendor_returns.id"), unique=True), *_timestamps(),
    )
    op.create_index("ux_vendor_returns_live_number", "vendor_returns", ["tenant_id", "return_number"], unique=True, postgresql_where=sa.text("deleted_at IS NULL"))
    op.create_table(
        "vendor_return_lines", _id_column(), sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False), sa.Column("vendor_return_id", UUID, sa.ForeignKey("vendor_returns.id"), nullable=False), sa.Column("purchase_receipt_line_id", UUID, sa.ForeignKey("purchase_receipt_lines.id")), sa.Column("core_obligation_id", UUID, sa.ForeignKey("core_obligations.id")), sa.Column("inventory_id", UUID, sa.ForeignKey("inventory.id"), nullable=False), sa.Column("quantity", sa.Integer(), nullable=False), sa.Column("expected_credit", sa.Numeric(12,2), nullable=False, server_default="0"), sa.Column("actual_credit", sa.Numeric(12,2)), sa.Column("stock_value_snapshot", sa.Numeric(12,2)), *_timestamps(),
    )
    op.create_table(
        "purchase_order_attachments", _id_column(), sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False), sa.Column("purchase_order_id", UUID, sa.ForeignKey("purchase_orders.id"), nullable=False), sa.Column("storage_key", sa.String(512), nullable=False), sa.Column("display_filename", sa.String(255), nullable=False), sa.Column("mime_type", sa.String(100), nullable=False), sa.Column("byte_size", sa.Integer(), nullable=False), sa.Column("sha256", sa.String(64), nullable=False), sa.Column("uploaded_by_user_id", UUID, sa.ForeignKey("users.id")), *_timestamps(),
    )

    op.execute("""
        INSERT INTO inventory_movements (tenant_id, inventory_id, bucket, movement_type, quantity_delta, balance_before, balance_after, unit_cost_snapshot, wac_before, wac_after, reason_code, occurred_at)
        SELECT tenant_id, id, 'on_hand', 'migration_opening_balance', stock_quantity, 0, stock_quantity, cost, cost, cost, '122_parts_operations_v1', now()
        FROM inventory WHERE deleted_at IS NULL AND stock_quantity > 0
    """)


def downgrade() -> None:
    # Drop every operational child first, then inventory's FK-bearing columns,
    # and only then the tenant catalog they reference. PostgreSQL correctly
    # rejects dropping inventory_categories while inventory.category_id exists.
    op.drop_index("ux_suppliers_live_normalized_name", table_name="suppliers")
    for table in (
        "purchase_order_attachments", "vendor_return_lines", "vendor_returns",
        "core_obligations", "purchase_receipt_lines", "purchase_receipts",
        "parts_operation_idempotency", "purchase_order_lines", "purchase_orders",
        "inventory_movements",
    ):
        op.drop_table(table)
    op.drop_index("ix_inventory_preferred_supplier_id", table_name="inventory")
    op.drop_index("ix_inventory_category_id", table_name="inventory")
    op.drop_column("inventory", "stock_version")
    op.drop_column("inventory", "preferred_supplier_id")
    op.drop_column("inventory", "category_id")
    op.drop_table("inventory_categories")
    op.drop_column("suppliers", "email")
    op.drop_column("suppliers", "account_reference")
    op.drop_column("suppliers", "is_active")
    op.drop_column("suppliers", "normalized_name")
    op.drop_column("tenants", "parts_operations_enabled")

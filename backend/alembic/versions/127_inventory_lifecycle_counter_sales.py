"""Add immutable part activity and dedicated counter-sale aggregates.

Revision ID: 127_inventory_lifecycle
Revises: 126_inventory_supplier_sources

The migration is intentionally schema-only.  Historical projection is handled
by the bounded ``backfill_part_activity`` command after live writers deploy.
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "127_inventory_lifecycle"
down_revision = "126_inventory_supplier_sources"
branch_labels = None
depends_on = None

UUID = postgresql.UUID(as_uuid=True)
JSON = postgresql.JSONB(astext_type=sa.Text())


def _identity_columns():
    return [
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    ]


def upgrade() -> None:
    op.add_column("tenants", sa.Column("counter_sales_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("quickbooks_connections", sa.Column("walk_in_customer_id", sa.String(64), nullable=True))

    op.create_table(
        "part_activity_events",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("inventory_id", UUID, sa.ForeignKey("inventory.id"), nullable=False),
        sa.Column("category", sa.String(32), nullable=False),
        sa.Column("event_type", sa.String(80), nullable=False),
        sa.Column("occurred_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("recorded_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("correlation_id", UUID, nullable=False),
        sa.Column("source_type", sa.String(48), nullable=True),
        sa.Column("source_id", UUID, nullable=True),
        sa.Column("source_number_snapshot", sa.String(120), nullable=True),
        sa.Column("part_sku_snapshot", sa.String(100), nullable=False),
        sa.Column("part_name_snapshot", sa.String(255), nullable=False),
        sa.Column("actor_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("actor_name_snapshot", sa.String(255), nullable=False),
        sa.Column("reason_code", sa.String(80), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("origin", sa.String(24), nullable=False),
        sa.Column("payload_version", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("before_values", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("after_values", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("stock_snapshot", JSON, nullable=True),
        sa.Column("money_snapshot", JSON, nullable=True),
        sa.Column("payment_snapshot", JSON, nullable=True),
        sa.Column("source_snapshot", JSON, nullable=True),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_part_activity_tenant_idempotency"),
        sa.ForeignKeyConstraint(["tenant_id", "inventory_id"], ["inventory.tenant_id", "inventory.id"], name="fk_part_activity_tenant_inventory"),
        sa.CheckConstraint("category IN ('catalog','stock','repairs','purchasing','returns','sales')", name="ck_part_activity_category"),
        sa.CheckConstraint("origin IN ('live','baseline','backfill_snapshot')", name="ck_part_activity_origin"),
    )
    op.create_index("ix_part_activity_tenant_occurred", "part_activity_events", ["tenant_id", sa.text("occurred_at DESC"), sa.text("id DESC")])
    op.create_index("ix_part_activity_part_occurred", "part_activity_events", ["tenant_id", "inventory_id", sa.text("occurred_at DESC"), sa.text("id DESC")])
    op.create_index("ix_part_activity_category_type", "part_activity_events", ["tenant_id", "category", "event_type"])
    op.create_index("ix_part_activity_actor", "part_activity_events", ["tenant_id", "actor_id"])
    op.create_index("ix_part_activity_source", "part_activity_events", ["tenant_id", "source_type", "source_id"])
    op.execute("""
        CREATE INDEX ix_part_activity_safe_search ON part_activity_events USING gin (
          to_tsvector('simple', coalesce(actor_name_snapshot,'') || ' ' ||
            coalesce(reason_code,'') || ' ' || coalesce(note,'') || ' ' ||
            coalesce(source_number_snapshot,'') || ' ' ||
            coalesce(part_sku_snapshot,'') || ' ' || coalesce(part_name_snapshot,''))
        )
    """)
    op.execute("""
        CREATE FUNCTION reject_part_activity_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'part_activity_events is append-only';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_part_activity_no_update_delete
        BEFORE UPDATE OR DELETE ON part_activity_events
        FOR EACH ROW EXECUTE FUNCTION reject_part_activity_mutation()
    """)

    op.create_table(
        "part_activity_backfill_runs",
        *_identity_columns(),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("payload_version", sa.SmallInteger(), nullable=False, server_default="1"),
        sa.Column("cutoff_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("batch_cursor", sa.String(255), nullable=True),
        sa.Column("source_counts", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("inserted_counts", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("replayed_counts", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("source_checksums", JSON, nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("duplicate_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text(), nullable=True),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("tenant_id", "payload_version", "cutoff_at", name="uq_activity_backfill_run"),
        sa.CheckConstraint("state IN ('running','failed','reconciled','verified')", name="ck_activity_backfill_state"),
    )
    op.create_index("ix_part_activity_backfill_runs_tenant_id", "part_activity_backfill_runs", ["tenant_id"])

    op.create_unique_constraint("uq_customers_tenant_id_id_db045", "customers", ["tenant_id", "id"])
    op.create_table(
        "counter_sales",
        *_identity_columns(),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("sale_number", sa.String(100), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("customer_id", UUID, nullable=True),
        sa.Column("buyer_name_snapshot", sa.String(255), nullable=True),
        sa.Column("buyer_email_snapshot", sa.String(255), nullable=True),
        sa.Column("buyer_phone_snapshot", sa.String(40), nullable=True),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("tax_rate_snapshot", sa.Numeric(7, 4), nullable=False, server_default="0"),
        sa.Column("service_fee_rate_snapshot", sa.Numeric(7, 4), nullable=False, server_default="0"),
        sa.Column("list_subtotal", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("charged_subtotal", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("discount_total", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("tax_total", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("service_fee_total", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("updated_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("completed_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("cancelled_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accounting_sync_status", sa.String(32), nullable=False, server_default="not_queued"),
        sa.Column("accounting_sales_receipt_id", sa.String(128), nullable=True),
        sa.Column("receipt_snapshot", JSON, nullable=True),
        sa.Column("receipt_email_to", sa.String(255), nullable=True),
        sa.UniqueConstraint("tenant_id", "id", name="uq_counter_sales_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "sale_number", name="uq_counter_sales_tenant_number"),
        sa.ForeignKeyConstraint(["tenant_id", "customer_id"], ["customers.tenant_id", "customers.id"], name="fk_counter_sales_tenant_customer"),
        sa.CheckConstraint("status IN ('draft','awaiting_payment','completed','partially_returned','returned','cancelled')", name="ck_counter_sale_status"),
        sa.CheckConstraint("currency = 'USD'", name="ck_counter_sale_currency"),
        sa.CheckConstraint("version >= 1", name="ck_counter_sale_version"),
    )
    op.create_index("ix_counter_sales_tenant_status", "counter_sales", ["tenant_id", "status", sa.text("created_at DESC")])
    op.create_index("ix_counter_sales_tenant_completed", "counter_sales", ["tenant_id", "completed_at"])

    op.create_table(
        "counter_sale_lines",
        *_identity_columns(),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("sale_id", UUID, sa.ForeignKey("counter_sales.id"), nullable=False),
        sa.Column("inventory_id", UUID, sa.ForeignKey("inventory.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("sku_snapshot", sa.String(100), nullable=False),
        sa.Column("name_snapshot", sa.String(255), nullable=False),
        sa.Column("unit_snapshot", sa.String(20), nullable=False),
        sa.Column("category_snapshot", sa.String(100), nullable=True),
        sa.Column("unit_cost", sa.Numeric(14, 2), nullable=False),
        sa.Column("list_unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("charged_unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("discount_total", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("item_subtotal", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_allocation", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("fee_allocation", sa.Numeric(14, 2), nullable=False, server_default="0"),
        sa.Column("total", sa.Numeric(14, 2), nullable=False),
        sa.Column("cost_total", sa.Numeric(14, 2), nullable=False),
        sa.Column("price_override_reason", sa.Text(), nullable=True),
        sa.Column("price_override_actor_id", UUID, sa.ForeignKey("users.id"), nullable=True),
        sa.Column("unit_allocations", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.UniqueConstraint("tenant_id", "id", name="uq_counter_sale_lines_tenant_id_id"),
        sa.UniqueConstraint("tenant_id", "sale_id", "id", name="uq_counter_sale_lines_tenant_sale_id"),
        sa.ForeignKeyConstraint(["tenant_id", "sale_id"], ["counter_sales.tenant_id", "counter_sales.id"], name="fk_counter_sale_lines_tenant_sale"),
        sa.ForeignKeyConstraint(["tenant_id", "inventory_id"], ["inventory.tenant_id", "inventory.id"], name="fk_counter_sale_lines_tenant_inventory"),
        sa.CheckConstraint("quantity > 0", name="ck_counter_sale_line_quantity"),
        sa.CheckConstraint("list_unit_price >= 0 AND charged_unit_price > 0", name="ck_counter_sale_line_prices"),
    )
    op.create_index("ix_counter_sale_lines_sale", "counter_sale_lines", ["tenant_id", "sale_id"])
    op.create_index("ix_counter_sale_lines_inventory", "counter_sale_lines", ["tenant_id", "inventory_id"])

    op.create_table(
        "counter_sale_reservations",
        *_identity_columns(),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("sale_id", UUID, sa.ForeignKey("counter_sales.id"), nullable=False),
        sa.Column("sale_line_id", UUID, sa.ForeignKey("counter_sale_lines.id"), nullable=False),
        sa.Column("inventory_id", UUID, sa.ForeignKey("inventory.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("state", sa.String(16), nullable=False, server_default="held"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("held_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("release_reason", sa.String(100), nullable=True),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.UniqueConstraint("tenant_id", "sale_line_id", name="uq_counter_sale_reservation_line"),
        sa.ForeignKeyConstraint(["tenant_id", "sale_id"], ["counter_sales.tenant_id", "counter_sales.id"], name="fk_counter_sale_reservations_tenant_sale"),
        sa.ForeignKeyConstraint(["tenant_id", "sale_id", "sale_line_id"], ["counter_sale_lines.tenant_id", "counter_sale_lines.sale_id", "counter_sale_lines.id"], name="fk_counter_sale_reservations_tenant_sale_line"),
        sa.ForeignKeyConstraint(["tenant_id", "inventory_id"], ["inventory.tenant_id", "inventory.id"], name="fk_counter_sale_reservations_tenant_inventory"),
        sa.CheckConstraint("quantity > 0", name="ck_counter_sale_reservation_quantity"),
        sa.CheckConstraint("state IN ('held','consumed','released','expired')", name="ck_counter_sale_reservation_state"),
    )
    op.create_index("ix_counter_sale_reservations_active", "counter_sale_reservations", ["tenant_id", "inventory_id", "state", "expires_at"])

    op.create_table(
        "counter_sale_payment_attempts",
        *_identity_columns(),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("sale_id", UUID, sa.ForeignKey("counter_sales.id"), nullable=False),
        sa.Column("tender", sa.String(32), nullable=False),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(3), nullable=False, server_default="USD"),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("provider_intent_id", sa.String(255), nullable=True),
        sa.Column("provider_charge_id", sa.String(255), nullable=True),
        sa.Column("provider_reference", sa.String(255), nullable=True),
        sa.Column("provider_request_id", sa.String(255), nullable=True),
        sa.Column("provider_status", sa.String(80), nullable=True),
        sa.Column("safe_failure_code", sa.String(100), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("actor_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_counter_sale_attempt_idempotency"),
        sa.UniqueConstraint("tenant_id", "id", name="uq_counter_sale_attempts_tenant_id_id"),
        sa.ForeignKeyConstraint(["tenant_id", "sale_id"], ["counter_sales.tenant_id", "counter_sales.id"], name="fk_counter_sale_attempts_tenant_sale"),
        sa.CheckConstraint("state IN ('created','pending','succeeded','failed','cancelled','compensating_refund_pending','compensated')", name="ck_counter_sale_attempt_state"),
        sa.CheckConstraint("amount > 0", name="ck_counter_sale_attempt_amount"),
    )
    op.create_index("ix_counter_sale_attempt_sale", "counter_sale_payment_attempts", ["tenant_id", "sale_id"])
    op.create_index("ix_counter_sale_attempt_provider", "counter_sale_payment_attempts", ["provider_charge_id", "provider_intent_id"])

    op.create_table(
        "counter_sale_provider_events",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("provider", sa.String(32), nullable=False),
        sa.Column("external_event_id", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(120), nullable=False),
        sa.Column("safe_payload_hash", sa.String(64), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("processing_state", sa.String(24), nullable=False),
        sa.Column("safe_error_summary", sa.Text(), nullable=True),
        sa.UniqueConstraint("provider", "external_event_id", name="uq_counter_sale_provider_event"),
        sa.CheckConstraint("processing_state IN ('received','processed','failed')", name="ck_counter_sale_provider_event_state"),
    )

    op.create_table(
        "counter_sale_returns",
        *_identity_columns(),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("sale_id", UUID, sa.ForeignKey("counter_sales.id"), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("state", sa.String(24), nullable=False),
        sa.Column("item_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("fee_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("refund_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("created_by_user_id", UUID, sa.ForeignKey("users.id"), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("correlation_id", UUID, nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accounting_refund_receipt_id", sa.String(128), nullable=True),
        sa.UniqueConstraint("tenant_id", "id", name="uq_counter_sale_returns_tenant_id_id"),
        sa.ForeignKeyConstraint(["tenant_id", "sale_id"], ["counter_sales.tenant_id", "counter_sales.id"], name="fk_counter_sale_returns_tenant_sale"),
        sa.CheckConstraint("state IN ('pending_refund','refund_failed','completed')", name="ck_counter_sale_return_state"),
        sa.CheckConstraint("version >= 1", name="ck_counter_sale_return_version"),
    )
    op.create_index("ix_counter_sale_returns_sale", "counter_sale_returns", ["tenant_id", "sale_id"])

    op.create_table(
        "counter_sale_return_lines",
        *_identity_columns(),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("return_id", UUID, sa.ForeignKey("counter_sale_returns.id"), nullable=False),
        sa.Column("sale_line_id", UUID, sa.ForeignKey("counter_sale_lines.id"), nullable=False),
        sa.Column("quantity", sa.Integer(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("disposition", sa.String(16), nullable=False),
        sa.Column("item_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("discount_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("tax_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("fee_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("cost_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("unit_ordinals", JSON, nullable=False, server_default=sa.text("'[]'::jsonb")),
        sa.ForeignKeyConstraint(["tenant_id", "return_id"], ["counter_sale_returns.tenant_id", "counter_sale_returns.id"], name="fk_counter_sale_return_lines_tenant_return"),
        sa.ForeignKeyConstraint(["tenant_id", "sale_line_id"], ["counter_sale_lines.tenant_id", "counter_sale_lines.id"], name="fk_counter_sale_return_lines_tenant_sale_line"),
        sa.CheckConstraint("quantity > 0", name="ck_counter_sale_return_line_quantity"),
        sa.CheckConstraint("disposition IN ('restock','damaged')", name="ck_counter_sale_return_disposition"),
    )

    op.create_table(
        "counter_sale_refunds",
        *_identity_columns(),
        sa.Column("tenant_id", UUID, sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("return_id", UUID, sa.ForeignKey("counter_sale_returns.id"), nullable=False),
        sa.Column("payment_attempt_id", UUID, sa.ForeignKey("counter_sale_payment_attempts.id"), nullable=False),
        sa.Column("tender", sa.String(32), nullable=False),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("provider_refund_id", sa.String(255), nullable=True),
        sa.Column("provider_reference", sa.String(255), nullable=True),
        sa.Column("idempotency_key", sa.String(128), nullable=False),
        sa.Column("request_fingerprint", sa.String(64), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("safe_failure_code", sa.String(100), nullable=True),
        sa.UniqueConstraint("tenant_id", "idempotency_key", name="uq_counter_sale_refund_idempotency"),
        sa.ForeignKeyConstraint(["tenant_id", "return_id"], ["counter_sale_returns.tenant_id", "counter_sale_returns.id"], name="fk_counter_sale_refunds_tenant_return"),
        sa.ForeignKeyConstraint(["tenant_id", "payment_attempt_id"], ["counter_sale_payment_attempts.tenant_id", "counter_sale_payment_attempts.id"], name="fk_counter_sale_refunds_tenant_attempt"),
        sa.CheckConstraint("state IN ('pending','succeeded','failed')", name="ck_counter_sale_refund_state"),
        sa.CheckConstraint("amount > 0", name="ck_counter_sale_refund_amount"),
    )


def downgrade() -> None:
    # Downgrade is for fresh disposable verification only.  Refuse to erase
    # financial/audit history if any of the protected tables contain rows.
    bind = op.get_bind()
    if bind.dialect.name == "postgresql":
        bind.execute(sa.text("""
            DO $$ BEGIN
              IF EXISTS (SELECT 1 FROM part_activity_events LIMIT 1)
                 OR EXISTS (SELECT 1 FROM counter_sales LIMIT 1) THEN
                RAISE EXCEPTION 'DB-045 downgrade refused: immutable/financial rows exist';
              END IF;
            END $$
        """))
    for table in (
        "counter_sale_refunds", "counter_sale_return_lines", "counter_sale_returns",
        "counter_sale_provider_events", "counter_sale_payment_attempts",
        "counter_sale_reservations", "counter_sale_lines", "counter_sales",
        "part_activity_backfill_runs",
    ):
        op.drop_table(table)
    op.execute("DROP TRIGGER IF EXISTS trg_part_activity_no_update_delete ON part_activity_events")
    op.execute("DROP FUNCTION IF EXISTS reject_part_activity_mutation()")
    op.drop_table("part_activity_events")
    op.drop_constraint("uq_customers_tenant_id_id_db045", "customers", type_="unique")
    op.drop_column("quickbooks_connections", "walk_in_customer_id")
    op.drop_column("tenants", "counter_sales_enabled")

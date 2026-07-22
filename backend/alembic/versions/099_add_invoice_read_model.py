"""add transactionally maintained invoice list read model

Revision ID: 099_invoice_read_model
Revises: 098_merge_repair_invoice_heads
"""
from alembic import op
import sqlalchemy as sa


revision = "099_invoice_read_model"
down_revision = "098_merge_repair_invoice_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "invoice_read_models",
        sa.Column("invoice_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("repair_order_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["invoice_id"], ["invoices.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["repair_order_id"], ["repair_orders.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.PrimaryKeyConstraint("invoice_id"),
    )
    for name, columns in (
        ("ix_invoice_read_models_tenant_created", ["tenant_id", "created_at"]),
        ("ix_invoice_read_models_tenant_status_created", ["tenant_id", "status", "created_at"]),
        ("ix_invoice_read_models_tenant_order_created", ["tenant_id", "repair_order_id", "created_at"]),
        ("ix_invoice_read_models_customer_created", ["customer_id", "created_at"]),
    ):
        op.create_index(name, "invoice_read_models", columns)

    op.execute("""
      CREATE FUNCTION refresh_invoice_read_model(target_invoice_id uuid) RETURNS void LANGUAGE plpgsql AS $$
      BEGIN
        DELETE FROM invoice_read_models WHERE invoice_id = target_invoice_id;
        INSERT INTO invoice_read_models (invoice_id, tenant_id, repair_order_id, customer_id, status, created_at, payload, refreshed_at)
        SELECT invoice.id, invoice.tenant_id, invoice.repair_order_id, repair_order.customer_id, invoice.status::text, invoice.created_at,
          jsonb_build_object(
            'id', invoice.id, 'tenant_id', invoice.tenant_id, 'repair_order_id', invoice.repair_order_id,
            'invoice_number', invoice.invoice_number, 'status', invoice.status::text, 'is_internal', invoice.is_internal,
            'subtotal', invoice.subtotal, 'shop_supplies_amount', invoice.shop_supplies_amount, 'service_fee_amount', invoice.service_fee_amount,
            'tax_amount', invoice.tax_amount, 'discount_amount', invoice.discount_amount, 'total_amount', invoice.total_amount,
            'due_date', invoice.due_date, 'paid_at', invoice.paid_at, 'notes', invoice.notes,
            'voided_at', invoice.voided_at, 'voided_by_user_id', invoice.voided_by_user_id, 'void_reason', invoice.void_reason,
            'supersedes_invoice_id', invoice.supersedes_invoice_id,
            'pending_zelle_confirmation', coalesce(invoice.zelle_pending_submitted_at IS NOT NULL AND invoice.status::text <> 'paid', false),
            'zelle_pending_submitted_at', invoice.zelle_pending_submitted_at, 'zelle_pending_sender_email', invoice.zelle_pending_sender_email,
            'zelle_pending_sender_phone', invoice.zelle_pending_sender_phone, 'zelle_pending_last_reminder_at', invoice.zelle_pending_last_reminder_at,
            'zelle_pending_reminder_count', invoice.zelle_pending_reminder_count, 'last_reminder_sent_at', invoice.last_reminder_sent_at,
            'reminder_count', invoice.reminder_count, 'created_at', invoice.created_at, 'updated_at', invoice.updated_at,
            'payment', payment.payload
          ), now()
        FROM invoices invoice JOIN repair_orders repair_order ON repair_order.id = invoice.repair_order_id
        LEFT JOIN LATERAL (
          SELECT jsonb_build_object('amount', p.amount, 'method', p.method::text, 'paid_at', p.created_at,
            'recorded_by_name', nullif(concat_ws(' ', u.first_name, u.last_name), ''),
            'payment_provider', p.payment_provider, 'reference_number', p.reference_number, 'authorization_number', p.authorization_number) payload
          FROM payments p LEFT JOIN users u ON u.id = p.recorded_by_user_id
          WHERE p.invoice_id = invoice.id AND p.status::text = 'completed'
          ORDER BY p.created_at DESC LIMIT 1
        ) payment ON invoice.status::text = 'paid'
        WHERE invoice.id = target_invoice_id;
      END; $$
    """)
    op.execute("""CREATE FUNCTION refresh_invoice_read_model_from_invoice() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM refresh_invoice_read_model(CASE WHEN TG_OP = 'DELETE' THEN OLD.id ELSE NEW.id END); RETURN NULL; END; $$""")
    op.execute("""CREATE FUNCTION refresh_invoice_read_model_from_payment() RETURNS trigger LANGUAGE plpgsql AS $$ BEGIN PERFORM refresh_invoice_read_model(CASE WHEN TG_OP = 'DELETE' THEN OLD.invoice_id ELSE NEW.invoice_id END); RETURN NULL; END; $$""")
    op.execute("""CREATE FUNCTION refresh_invoice_read_models_from_repair_order() RETURNS trigger LANGUAGE plpgsql AS $$ DECLARE r record; BEGIN FOR r IN SELECT id FROM invoices WHERE repair_order_id = NEW.id LOOP PERFORM refresh_invoice_read_model(r.id); END LOOP; RETURN NULL; END; $$""")
    op.execute("CREATE TRIGGER invoice_read_model_invoice AFTER INSERT OR UPDATE OR DELETE ON invoices FOR EACH ROW EXECUTE FUNCTION refresh_invoice_read_model_from_invoice()")
    op.execute("CREATE TRIGGER invoice_read_model_payment AFTER INSERT OR UPDATE OR DELETE ON payments FOR EACH ROW EXECUTE FUNCTION refresh_invoice_read_model_from_payment()")
    op.execute("CREATE TRIGGER invoice_read_model_repair_order AFTER UPDATE OF customer_id ON repair_orders FOR EACH ROW EXECUTE FUNCTION refresh_invoice_read_models_from_repair_order()")
    op.execute("SELECT refresh_invoice_read_model(id) FROM invoices")


def downgrade() -> None:
    for trigger, table in (("invoice_read_model_repair_order", "repair_orders"), ("invoice_read_model_payment", "payments"), ("invoice_read_model_invoice", "invoices")):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
    for function in ("refresh_invoice_read_models_from_repair_order()", "refresh_invoice_read_model_from_payment()", "refresh_invoice_read_model_from_invoice()", "refresh_invoice_read_model(uuid)"):
        op.execute(f"DROP FUNCTION IF EXISTS {function}")
    for index in ("ix_invoice_read_models_customer_created", "ix_invoice_read_models_tenant_order_created", "ix_invoice_read_models_tenant_status_created", "ix_invoice_read_models_tenant_created"):
        op.drop_index(index, table_name="invoice_read_models")
    op.drop_table("invoice_read_models")

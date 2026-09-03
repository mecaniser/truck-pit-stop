"""Keep paid-invoice read models aligned with PaymentSummary.

Revision ID: 134_invoice_payment_projection
Revises: 133_invoice_partial_payments
"""
from alembic import op


revision = "134_invoice_payment_projection"
down_revision = "133_invoice_partial_payments"
branch_labels = None
depends_on = None


def _refresh_function_sql(*, include_payment_identity: bool) -> str:
    payment_identity = ""
    if include_payment_identity:
        payment_identity = """
            'id', p.id,
            'quickbooks_charge_status', p.quickbooks_charge_status,
            'quickbooks_reconciled_at', p.quickbooks_reconciled_at,
        """

    return f"""
      CREATE OR REPLACE FUNCTION refresh_invoice_read_model(target_invoice_id uuid)
      RETURNS void LANGUAGE plpgsql AS $$
      BEGIN
        DELETE FROM invoice_read_models WHERE invoice_id = target_invoice_id;
        INSERT INTO invoice_read_models (
          invoice_id, tenant_id, repair_order_id, customer_id, status,
          created_at, payload, refreshed_at
        )
        SELECT
          invoice.id, invoice.tenant_id, invoice.repair_order_id,
          repair_order.customer_id, invoice.status::text, invoice.created_at,
          jsonb_build_object(
            'id', invoice.id,
            'tenant_id', invoice.tenant_id,
            'repair_order_id', invoice.repair_order_id,
            'invoice_number', invoice.invoice_number,
            'status', invoice.status::text,
            'is_internal', invoice.is_internal,
            'subtotal', invoice.subtotal,
            'shop_supplies_amount', invoice.shop_supplies_amount,
            'service_fee_amount', invoice.service_fee_amount,
            'tax_amount', invoice.tax_amount,
            'discount_amount', invoice.discount_amount,
            'total_amount', invoice.total_amount,
            'due_date', invoice.due_date,
            'paid_at', invoice.paid_at,
            'notes', invoice.notes,
            'voided_at', invoice.voided_at,
            'voided_by_user_id', invoice.voided_by_user_id,
            'void_reason', invoice.void_reason,
            'supersedes_invoice_id', invoice.supersedes_invoice_id,
            'pending_zelle_confirmation', coalesce(
              invoice.zelle_pending_submitted_at IS NOT NULL
              AND invoice.status::text <> 'paid',
              false
            ),
            'zelle_pending_submitted_at', invoice.zelle_pending_submitted_at,
            'zelle_pending_sender_email', invoice.zelle_pending_sender_email,
            'zelle_pending_sender_phone', invoice.zelle_pending_sender_phone,
            'zelle_pending_last_reminder_at',
              invoice.zelle_pending_last_reminder_at,
            'zelle_pending_reminder_count', invoice.zelle_pending_reminder_count,
            'last_reminder_sent_at', invoice.last_reminder_sent_at,
            'reminder_count', invoice.reminder_count,
            'created_at', invoice.created_at,
            'updated_at', invoice.updated_at,
            'payment', payment.payload
          ),
          now()
        FROM invoices invoice
        JOIN repair_orders repair_order
          ON repair_order.id = invoice.repair_order_id
        LEFT JOIN LATERAL (
          SELECT jsonb_build_object(
            {payment_identity}
            'amount', p.amount,
            'method', p.method::text,
            'paid_at', p.created_at,
            'recorded_by_name',
              nullif(concat_ws(' ', u.first_name, u.last_name), ''),
            'payment_provider', p.payment_provider,
            'reference_number', p.reference_number,
            'authorization_number', p.authorization_number
          ) payload
          FROM payments p
          LEFT JOIN users u ON u.id = p.recorded_by_user_id
          WHERE p.invoice_id = invoice.id
            AND p.status::text = 'completed'
          ORDER BY p.created_at DESC
          LIMIT 1
        ) payment ON invoice.status::text = 'paid'
        WHERE invoice.id = target_invoice_id;
      END;
      $$
    """


def upgrade() -> None:
    op.execute(_refresh_function_sql(include_payment_identity=True))
    op.execute("SELECT refresh_invoice_read_model(id) FROM invoices")


def downgrade() -> None:
    op.execute(_refresh_function_sql(include_payment_identity=False))
    op.execute("SELECT refresh_invoice_read_model(id) FROM invoices")

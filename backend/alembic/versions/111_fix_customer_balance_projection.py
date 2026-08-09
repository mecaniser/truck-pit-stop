"""fix customer balance projection and backfill balances

Revision ID: 111_customer_balance
Revises: 110_safe_vehicle_merge
"""

from alembic import op


revision = "111_customer_balance"
down_revision = "110_safe_vehicle_merge"
branch_labels = None
depends_on = None


def _replace_refresh_function(*, corrected: bool) -> None:
    vehicle_filter = "AND deleted_at IS NULL" if corrected else ""
    invoice_filter = "AND invoice.status <> 'cancelled'" if corrected else ""
    payment_filter = (
        "AND invoice.status <> 'cancelled' AND payment.status = 'completed'"
        if corrected
        else ""
    )
    op.execute(
        f"""
        CREATE OR REPLACE FUNCTION refresh_customer_read_model(target_customer_id uuid)
        RETURNS void LANGUAGE plpgsql AS $$
        BEGIN
          INSERT INTO customer_read_models (
            customer_id, tenant_id, vehicle_count, single_vehicle_license_plate,
            invoice_total, payment_total, refreshed_at
          )
          SELECT
            customer.id,
            customer.tenant_id,
            (
              SELECT count(*)::integer
              FROM vehicles
              WHERE customer_id = customer.id
              {vehicle_filter}
            ),
            (
              SELECT max(license_plate)
              FROM vehicles
              WHERE customer_id = customer.id
              {vehicle_filter}
              HAVING count(*) = 1
            ),
            COALESCE((
              SELECT sum(invoice.total_amount)
              FROM repair_orders repair_order
              JOIN invoices invoice ON invoice.repair_order_id = repair_order.id
              WHERE repair_order.customer_id = customer.id
              {invoice_filter}
            ), 0),
            COALESCE((
              SELECT sum(payment.amount)
              FROM repair_orders repair_order
              JOIN invoices invoice ON invoice.repair_order_id = repair_order.id
              JOIN payments payment ON payment.invoice_id = invoice.id
              WHERE repair_order.customer_id = customer.id
              {payment_filter}
            ), 0),
            now()
          FROM customers customer
          WHERE customer.id = target_customer_id
          ON CONFLICT (customer_id) DO UPDATE SET
            tenant_id = EXCLUDED.tenant_id,
            vehicle_count = EXCLUDED.vehicle_count,
            single_vehicle_license_plate = EXCLUDED.single_vehicle_license_plate,
            invoice_total = EXCLUDED.invoice_total,
            payment_total = EXCLUDED.payment_total,
            refreshed_at = EXCLUDED.refreshed_at;
        END;
        $$
        """
    )


def _replace_financial_triggers(*, corrected: bool) -> None:
    op.execute("DROP TRIGGER IF EXISTS customer_read_model_invoice ON invoices")
    op.execute("DROP TRIGGER IF EXISTS customer_read_model_payment ON payments")
    invoice_columns = "repair_order_id, total_amount, status" if corrected else "repair_order_id, total_amount"
    payment_columns = "invoice_id, amount, status" if corrected else "invoice_id, amount"
    op.execute(
        "CREATE TRIGGER customer_read_model_invoice "
        f"AFTER INSERT OR DELETE OR UPDATE OF {invoice_columns} ON invoices "
        "FOR EACH ROW EXECUTE FUNCTION refresh_customer_read_model_from_invoice()"
    )
    op.execute(
        "CREATE TRIGGER customer_read_model_payment "
        f"AFTER INSERT OR DELETE OR UPDATE OF {payment_columns} ON payments "
        "FOR EACH ROW EXECUTE FUNCTION refresh_customer_read_model_from_payment()"
    )


def _replace_vehicle_trigger(*, corrected: bool) -> None:
    op.execute("DROP TRIGGER IF EXISTS customer_read_model_vehicle ON vehicles")
    vehicle_columns = "customer_id, license_plate, deleted_at" if corrected else "customer_id, license_plate"
    op.execute(
        "CREATE TRIGGER customer_read_model_vehicle "
        f"AFTER INSERT OR DELETE OR UPDATE OF {vehicle_columns} ON vehicles "
        "FOR EACH ROW EXECUTE FUNCTION refresh_customer_read_model_from_vehicle()"
    )


def upgrade() -> None:
    _replace_refresh_function(corrected=True)
    _replace_financial_triggers(corrected=True)
    _replace_vehicle_trigger(corrected=True)
    op.execute("SELECT refresh_customer_read_model(id) FROM customers")


def downgrade() -> None:
    _replace_refresh_function(corrected=False)
    _replace_financial_triggers(corrected=False)
    _replace_vehicle_trigger(corrected=False)
    op.execute("SELECT refresh_customer_read_model(id) FROM customers")

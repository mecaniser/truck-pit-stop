"""add transactionally maintained customer list read model

Revision ID: 091
Revises: 090
"""
from alembic import op
import sqlalchemy as sa


revision = "091"
down_revision = "090"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "customer_read_models",
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("vehicle_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("single_vehicle_license_plate", sa.String(length=20), nullable=True),
        sa.Column("invoice_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("payment_total", sa.Numeric(12, 2), nullable=False, server_default="0"),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("customer_id"),
    )
    op.create_index("ix_customer_read_models_tenant_id", "customer_read_models", ["tenant_id"])
    op.execute(
        "CREATE INDEX ix_customer_read_models_tenant_balance "
        "ON customer_read_models (tenant_id, (invoice_total - payment_total), customer_id)"
    )
    op.create_index(
        "ix_customer_read_models_tenant_vehicle_count",
        "customer_read_models",
        ["tenant_id", "vehicle_count", "customer_id"],
    )

    # A single canonical recalculation function keeps the projection correct
    # for every writer, including imports and scripts that bypass the API.
    op.execute(
        """
        CREATE FUNCTION refresh_customer_read_model(target_customer_id uuid)
        RETURNS void LANGUAGE plpgsql AS $$
        BEGIN
          INSERT INTO customer_read_models (
            customer_id, tenant_id, vehicle_count, single_vehicle_license_plate,
            invoice_total, payment_total, refreshed_at
          )
          SELECT
            customer.id,
            customer.tenant_id,
            (SELECT count(*)::integer FROM vehicles WHERE customer_id = customer.id),
            (
              SELECT max(license_plate)
              FROM vehicles
              WHERE customer_id = customer.id
              HAVING count(*) = 1
            ),
            COALESCE((
              SELECT sum(invoice.total_amount)
              FROM repair_orders repair_order
              JOIN invoices invoice ON invoice.repair_order_id = repair_order.id
              WHERE repair_order.customer_id = customer.id
            ), 0),
            COALESCE((
              SELECT sum(payment.amount)
              FROM repair_orders repair_order
              JOIN invoices invoice ON invoice.repair_order_id = repair_order.id
              JOIN payments payment ON payment.invoice_id = invoice.id
              WHERE repair_order.customer_id = customer.id
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
    op.execute(
        """
        CREATE FUNCTION refresh_customer_read_model_from_vehicle()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM refresh_customer_read_model(CASE WHEN TG_OP = 'DELETE' THEN OLD.customer_id ELSE NEW.customer_id END);
          IF TG_OP = 'UPDATE' AND OLD.customer_id IS DISTINCT FROM NEW.customer_id THEN
            PERFORM refresh_customer_read_model(OLD.customer_id);
          END IF;
          RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION refresh_customer_read_model_from_repair_order()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM refresh_customer_read_model(CASE WHEN TG_OP = 'DELETE' THEN OLD.customer_id ELSE NEW.customer_id END);
          IF TG_OP = 'UPDATE' AND OLD.customer_id IS DISTINCT FROM NEW.customer_id THEN
            PERFORM refresh_customer_read_model(OLD.customer_id);
          END IF;
          RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION refresh_customer_read_model_from_invoice()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE target_repair_order_id uuid;
        BEGIN
          target_repair_order_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.repair_order_id ELSE NEW.repair_order_id END;
          PERFORM refresh_customer_read_model(customer_id) FROM repair_orders WHERE id = target_repair_order_id;
          IF TG_OP = 'UPDATE' AND OLD.repair_order_id IS DISTINCT FROM NEW.repair_order_id THEN
            PERFORM refresh_customer_read_model(customer_id) FROM repair_orders WHERE id = OLD.repair_order_id;
          END IF;
          RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION refresh_customer_read_model_from_payment()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE target_invoice_id uuid;
        BEGIN
          target_invoice_id := CASE WHEN TG_OP = 'DELETE' THEN OLD.invoice_id ELSE NEW.invoice_id END;
          PERFORM refresh_customer_read_model(repair_order.customer_id)
          FROM invoices invoice JOIN repair_orders repair_order ON repair_order.id = invoice.repair_order_id
          WHERE invoice.id = target_invoice_id;
          IF TG_OP = 'UPDATE' AND OLD.invoice_id IS DISTINCT FROM NEW.invoice_id THEN
            PERFORM refresh_customer_read_model(repair_order.customer_id)
            FROM invoices invoice JOIN repair_orders repair_order ON repair_order.id = invoice.repair_order_id
            WHERE invoice.id = OLD.invoice_id;
          END IF;
          RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION refresh_customer_read_model_from_customer()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM refresh_customer_read_model(NEW.id);
          RETURN NULL;
        END;
        $$
        """
    )
    op.execute("CREATE TRIGGER customer_read_model_customer AFTER INSERT ON customers FOR EACH ROW EXECUTE FUNCTION refresh_customer_read_model_from_customer()")
    op.execute("CREATE TRIGGER customer_read_model_vehicle AFTER INSERT OR DELETE OR UPDATE OF customer_id, license_plate ON vehicles FOR EACH ROW EXECUTE FUNCTION refresh_customer_read_model_from_vehicle()")
    op.execute("CREATE TRIGGER customer_read_model_repair_order AFTER INSERT OR DELETE OR UPDATE OF customer_id ON repair_orders FOR EACH ROW EXECUTE FUNCTION refresh_customer_read_model_from_repair_order()")
    op.execute("CREATE TRIGGER customer_read_model_invoice AFTER INSERT OR DELETE OR UPDATE OF repair_order_id, total_amount ON invoices FOR EACH ROW EXECUTE FUNCTION refresh_customer_read_model_from_invoice()")
    op.execute("CREATE TRIGGER customer_read_model_payment AFTER INSERT OR DELETE OR UPDATE OF invoice_id, amount ON payments FOR EACH ROW EXECUTE FUNCTION refresh_customer_read_model_from_payment()")

    op.execute("SELECT refresh_customer_read_model(id) FROM customers")


def downgrade() -> None:
    for trigger, table in (
        ("customer_read_model_payment", "payments"),
        ("customer_read_model_invoice", "invoices"),
        ("customer_read_model_repair_order", "repair_orders"),
        ("customer_read_model_vehicle", "vehicles"),
        ("customer_read_model_customer", "customers"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
    for function in (
        "refresh_customer_read_model_from_customer()",
        "refresh_customer_read_model_from_payment()",
        "refresh_customer_read_model_from_invoice()",
        "refresh_customer_read_model_from_repair_order()",
        "refresh_customer_read_model_from_vehicle()",
        "refresh_customer_read_model(uuid)",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {function}")
    op.drop_index("ix_customer_read_models_tenant_vehicle_count", table_name="customer_read_models")
    op.execute("DROP INDEX IF EXISTS ix_customer_read_models_tenant_balance")
    op.drop_index("ix_customer_read_models_tenant_id", table_name="customer_read_models")
    op.drop_table("customer_read_models")

"""add transactionally maintained repair-order list read model

Revision ID: 096_repair_order_read_model
Revises: 095_fleet_board_driver_phone
"""
from alembic import op
import sqlalchemy as sa


revision = "096_repair_order_read_model"
down_revision = "095_fleet_board_driver_phone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repair_order_read_models",
        sa.Column("repair_order_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("vehicle_id", sa.UUID(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("is_internal", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_deleted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("search_document", sa.Text(), nullable=False, server_default=""),
        sa.Column("search_compact", sa.Text(), nullable=False, server_default=""),
        sa.Column("payload", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["repair_order_id"], ["repair_orders.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"]),
        sa.PrimaryKeyConstraint("repair_order_id"),
    )
    op.create_index(
        "ix_repair_order_read_models_tenant_created",
        "repair_order_read_models",
        ["tenant_id", "is_deleted", "created_at"],
    )
    op.create_index(
        "ix_repair_order_read_models_tenant_customer_created",
        "repair_order_read_models",
        ["tenant_id", "customer_id", "is_deleted", "created_at"],
    )
    op.create_index(
        "ix_repair_order_read_models_tenant_vehicle_created",
        "repair_order_read_models",
        ["tenant_id", "vehicle_id", "is_deleted", "created_at"],
    )
    op.create_index(
        "ix_repair_order_read_models_tenant_status_created",
        "repair_order_read_models",
        ["tenant_id", "status", "is_deleted", "created_at"],
    )
    op.create_index(
        "ix_repair_order_read_models_tenant_internal_created",
        "repair_order_read_models",
        ["tenant_id", "is_internal", "is_deleted", "created_at"],
    )
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
    op.execute(
        "CREATE INDEX ix_repair_order_read_models_search_document_trgm "
        "ON repair_order_read_models USING gin (search_document gin_trgm_ops)"
    )
    op.execute(
        "CREATE INDEX ix_repair_order_read_models_search_compact_trgm "
        "ON repair_order_read_models USING gin (search_compact gin_trgm_ops)"
    )

    # This is the only place the projection is assembled. It deliberately
    # records the existing list response shape, including quote/invoice state,
    # so the read path never needs to reopen those tables.
    op.execute(
        """
        CREATE FUNCTION refresh_repair_order_read_model(target_repair_order_id uuid)
        RETURNS void LANGUAGE plpgsql AS $$
        BEGIN
          DELETE FROM repair_order_read_models WHERE repair_order_id = target_repair_order_id;

          INSERT INTO repair_order_read_models (
            repair_order_id, tenant_id, customer_id, vehicle_id, status,
            is_internal, is_deleted, created_at, search_document,
            search_compact, payload, refreshed_at
          )
          SELECT
            repair_order.id,
            repair_order.tenant_id,
            repair_order.customer_id,
            repair_order.vehicle_id,
            repair_order.status::text,
            repair_order.is_internal,
            repair_order.deleted_at IS NOT NULL,
            repair_order.created_at,
            concat_ws(' ',
              repair_order.order_number, repair_order.description,
              customer.first_name, customer.last_name, customer.company_name,
              customer.email, customer.phone, customer.usdot_number, customer.mc_number,
              vehicle.vin, vehicle.unit_number, vehicle.make, vehicle.model
            ),
            regexp_replace(concat_ws(' ', repair_order.order_number, vehicle.vin, vehicle.unit_number), '[^[:alnum:]]', '', 'g'),
            jsonb_build_object(
              'id', repair_order.id,
              'tenant_id', repair_order.tenant_id,
              'customer_id', repair_order.customer_id,
              'vehicle_id', repair_order.vehicle_id,
              'order_number', repair_order.order_number,
              'status', repair_order.status::text,
              'description', repair_order.description,
              'customer_notes', repair_order.customer_notes,
              'internal_notes', repair_order.internal_notes,
              'po_number', repair_order.po_number,
              'mileage_in', repair_order.mileage_in,
              'mileage_out', repair_order.mileage_out,
              'assigned_mechanic_id', repair_order.assigned_mechanic_id,
              'total_parts_cost', repair_order.total_parts_cost,
              'total_labor_cost', repair_order.total_labor_cost,
              'total_cost', repair_order.total_cost,
              'created_at', repair_order.created_at,
              'updated_at', repair_order.updated_at,
              'work_started_at', repair_order.work_started_at,
              'work_completed_at', repair_order.work_completed_at,
              'hold_reason', repair_order.hold_reason,
              'held_at', repair_order.held_at,
              'cancelled_at', repair_order.cancelled_at,
              'cancelled_by_user_id', repair_order.cancelled_by_user_id,
              'cancelled_by_name', nullif(concat_ws(' ', cancelled_by.first_name, cancelled_by.last_name), ''),
              'deleted_at', repair_order.deleted_at,
              'deleted_by_user_id', repair_order.deleted_by_user_id,
              'deleted_by_name', nullif(concat_ws(' ', deleted_by.first_name, deleted_by.last_name), ''),
              'estimated_labor_minutes', repair_order.estimated_labor_minutes,
              'actual_tracked_minutes', repair_order.actual_tracked_minutes,
              'total_hold_minutes', repair_order.total_hold_minutes,
              'assigned_at', repair_order.assigned_at,
              'acknowledged_at', repair_order.acknowledged_at,
              'pricing_locked_at', repair_order.pricing_locked_at,
              'pricing_lock_reason', repair_order.pricing_lock_reason,
              'quote_sent', quote.sent_to_customer,
              'quote_approved', quote.is_approved,
              'quote_sent_at', quote.sent_at,
              'invoice_created_at', invoice.created_at,
              'invoice_due_date', invoice.due_date,
              'pending_zelle_confirmation', coalesce(invoice.zelle_pending_submitted_at IS NOT NULL AND invoice.status::text <> 'paid', false),
              'parent_repair_order_id', repair_order.parent_repair_order_id,
              'is_warranty_repair', repair_order.is_warranty_repair,
              'is_internal', repair_order.is_internal,
              'bill_labor_at_customer_rate', repair_order.bill_labor_at_customer_rate,
              'is_pm', repair_order.is_pm,
              'vehicle_make', coalesce(vehicle.make, ''),
              'vehicle_model', coalesce(vehicle.model, ''),
              'vehicle_year', vehicle.year,
              'vehicle_unit_number', vehicle.unit_number,
              'vehicle_vin', vehicle.vin,
              'customer_first_name', coalesce(customer.first_name, ''),
              'customer_last_name', coalesce(customer.last_name, ''),
              'customer_company_name', customer.company_name,
              'customer_email', customer.email,
              'customer_phone', customer.phone
            ),
            now()
          FROM repair_orders repair_order
          JOIN customers customer ON customer.id = repair_order.customer_id
          JOIN vehicles vehicle ON vehicle.id = repair_order.vehicle_id
          LEFT JOIN quotes quote ON quote.repair_order_id = repair_order.id
          LEFT JOIN invoices invoice ON invoice.repair_order_id = repair_order.id
          LEFT JOIN users cancelled_by ON cancelled_by.id = repair_order.cancelled_by_user_id
          LEFT JOIN users deleted_by ON deleted_by.id = repair_order.deleted_by_user_id
          WHERE repair_order.id = target_repair_order_id;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION refresh_repair_order_read_model_from_repair_order()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM refresh_repair_order_read_model(CASE WHEN TG_OP = 'DELETE' THEN OLD.id ELSE NEW.id END);
          RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION refresh_repair_order_read_models_from_customer()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE order_row record;
        BEGIN
          FOR order_row IN SELECT id FROM repair_orders WHERE customer_id = CASE WHEN TG_OP = 'DELETE' THEN OLD.id ELSE NEW.id END LOOP
            PERFORM refresh_repair_order_read_model(order_row.id);
          END LOOP;
          RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION refresh_repair_order_read_models_from_vehicle()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE order_row record;
        BEGIN
          FOR order_row IN SELECT id FROM repair_orders WHERE vehicle_id = CASE WHEN TG_OP = 'DELETE' THEN OLD.id ELSE NEW.id END LOOP
            PERFORM refresh_repair_order_read_model(order_row.id);
          END LOOP;
          RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION refresh_repair_order_read_model_from_quote()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM refresh_repair_order_read_model(CASE WHEN TG_OP = 'DELETE' THEN OLD.repair_order_id ELSE NEW.repair_order_id END);
          RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION refresh_repair_order_read_model_from_invoice()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM refresh_repair_order_read_model(CASE WHEN TG_OP = 'DELETE' THEN OLD.repair_order_id ELSE NEW.repair_order_id END);
          RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION refresh_repair_order_read_models_from_user()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE order_row record;
        BEGIN
          FOR order_row IN
            SELECT id FROM repair_orders
            WHERE cancelled_by_user_id = NEW.id OR deleted_by_user_id = NEW.id
          LOOP
            PERFORM refresh_repair_order_read_model(order_row.id);
          END LOOP;
          RETURN NULL;
        END;
        $$
        """
    )
    op.execute("CREATE TRIGGER repair_order_read_model_repair_order AFTER INSERT OR UPDATE OR DELETE ON repair_orders FOR EACH ROW EXECUTE FUNCTION refresh_repair_order_read_model_from_repair_order()")
    op.execute("CREATE TRIGGER repair_order_read_model_customer AFTER UPDATE OF first_name, last_name, company_name, email, phone, usdot_number, mc_number ON customers FOR EACH ROW EXECUTE FUNCTION refresh_repair_order_read_models_from_customer()")
    op.execute("CREATE TRIGGER repair_order_read_model_vehicle AFTER UPDATE OF vin, unit_number, make, model, year ON vehicles FOR EACH ROW EXECUTE FUNCTION refresh_repair_order_read_models_from_vehicle()")
    op.execute("CREATE TRIGGER repair_order_read_model_quote AFTER INSERT OR UPDATE OR DELETE ON quotes FOR EACH ROW EXECUTE FUNCTION refresh_repair_order_read_model_from_quote()")
    op.execute("CREATE TRIGGER repair_order_read_model_invoice AFTER INSERT OR UPDATE OR DELETE ON invoices FOR EACH ROW EXECUTE FUNCTION refresh_repair_order_read_model_from_invoice()")
    op.execute("CREATE TRIGGER repair_order_read_model_user AFTER UPDATE OF first_name, last_name ON users FOR EACH ROW EXECUTE FUNCTION refresh_repair_order_read_models_from_user()")
    op.execute("SELECT refresh_repair_order_read_model(id) FROM repair_orders")


def downgrade() -> None:
    for trigger, table in (
        ("repair_order_read_model_user", "users"),
        ("repair_order_read_model_invoice", "invoices"),
        ("repair_order_read_model_quote", "quotes"),
        ("repair_order_read_model_vehicle", "vehicles"),
        ("repair_order_read_model_customer", "customers"),
        ("repair_order_read_model_repair_order", "repair_orders"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
    for function in (
        "refresh_repair_order_read_models_from_user()",
        "refresh_repair_order_read_model_from_invoice()",
        "refresh_repair_order_read_model_from_quote()",
        "refresh_repair_order_read_models_from_vehicle()",
        "refresh_repair_order_read_models_from_customer()",
        "refresh_repair_order_read_model_from_repair_order()",
        "refresh_repair_order_read_model(uuid)",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {function}")
    op.execute("DROP INDEX IF EXISTS ix_repair_order_read_models_search_compact_trgm")
    op.execute("DROP INDEX IF EXISTS ix_repair_order_read_models_search_document_trgm")
    for index in (
        "ix_repair_order_read_models_tenant_internal_created",
        "ix_repair_order_read_models_tenant_status_created",
        "ix_repair_order_read_models_tenant_vehicle_created",
        "ix_repair_order_read_models_tenant_customer_created",
        "ix_repair_order_read_models_tenant_created",
    ):
        op.drop_index(index, table_name="repair_order_read_models")
    op.drop_table("repair_order_read_models")

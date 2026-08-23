"""Select one canonical quote and invoice in the repair-order projection.

Revision ID: 119_ro_projection_cardinality
Revises: 118_authenticated_presentation
"""

from alembic import op


revision = "119_ro_projection_cardinality"
down_revision = "118_authenticated_presentation"
branch_labels = None
depends_on = None


def _projection_function_sql() -> str:
    quote_join = """
          LEFT JOIN LATERAL (
            SELECT candidate.sent_to_customer, candidate.is_approved, candidate.sent_at
            FROM quotes candidate
            WHERE candidate.repair_order_id = repair_order.id
              AND candidate.tenant_id = repair_order.tenant_id
              AND candidate.deleted_at IS NULL
            ORDER BY candidate.revision DESC, candidate.created_at DESC, candidate.id DESC
            LIMIT 1
          ) quote ON true
    """
    invoice_join = """
          LEFT JOIN LATERAL (
            SELECT candidate.created_at, candidate.due_date,
                   candidate.zelle_pending_submitted_at, candidate.status
            FROM invoices candidate
            WHERE candidate.repair_order_id = repair_order.id
              AND candidate.tenant_id = repair_order.tenant_id
              AND candidate.deleted_at IS NULL
              AND candidate.status::text <> 'cancelled'
            ORDER BY candidate.created_at DESC, candidate.id DESC
            LIMIT 1
          ) invoice ON true
    """

    return f"""
        CREATE OR REPLACE FUNCTION refresh_repair_order_read_model(target_repair_order_id uuid)
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
              'pricing_lock_reason', repair_order.pricing_lock_reason
            ) || jsonb_build_object(
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
          {quote_join}
          {invoice_join}
          LEFT JOIN users cancelled_by ON cancelled_by.id = repair_order.cancelled_by_user_id
          LEFT JOIN users deleted_by ON deleted_by.id = repair_order.deleted_by_user_id
          WHERE repair_order.id = target_repair_order_id;
        END;
        $$
    """


def upgrade() -> None:
    op.execute(_projection_function_sql())
    op.execute("SELECT refresh_repair_order_read_model(id) FROM repair_orders ORDER BY id")


def downgrade() -> None:
    # This is a forward-only correctness repair. Reinstalling revision 096's
    # Cartesian function would make existing multi-revision orders fail on the
    # next trigger. Retain the compatible function while Alembic moves the
    # version marker back; re-upgrade performs the deterministic backfill.
    op.execute(_projection_function_sql())

"""add driver phone to fleet board projection

Revision ID: 095_fleet_board_driver_phone
Revises: 094_merge_fleet_invoice_heads
"""
from alembic import op


revision = "095_fleet_board_driver_phone"
down_revision = "094_merge_fleet_invoice_heads"
branch_labels = None
depends_on = None


def _refresh_function(include_driver_phone: bool) -> str:
    driver_phone_line = "              'driver_phone', vehicle.driver_phone,\n" if include_driver_phone else ""
    return f"""
        CREATE OR REPLACE FUNCTION refresh_fleet_board_read_model(target_vehicle_id uuid)
        RETURNS void LANGUAGE plpgsql AS $$
        BEGIN
          DELETE FROM fleet_board_read_models WHERE vehicle_id = target_vehicle_id;

          INSERT INTO fleet_board_read_models (
            vehicle_id, tenant_id, vehicle_data, urgent_work_order, pm_work_order,
            open_work_order_count, open_incident_count, refreshed_at
          )
          SELECT
            vehicle.id,
            vehicle.tenant_id,
            jsonb_build_object(
              'unit_number', vehicle.unit_number,
              'year', vehicle.year,
              'make', vehicle.make,
              'model', vehicle.model,
              'brand_short', CASE WHEN vehicle.make IS NULL THEN NULL ELSE upper(left(vehicle.make, 2)) END,
              'body_type', vehicle.nhtsa_body_class,
              'vin', vehicle.vin,
              'plate', vehicle.license_plate,
              'driver_name', vehicle.driver_name,
{driver_phone_line}              'mileage', vehicle.mileage,
              'pm_interval_miles', coalesce(vehicle.pm_interval_miles, 25000),
              'next_pm_miles', vehicle.next_pm_miles,
              'pm_remaining', CASE WHEN vehicle.next_pm_miles IS NULL OR vehicle.mileage IS NULL THEN NULL ELSE vehicle.next_pm_miles - vehicle.mileage END,
              'pm_interval_days', coalesce(vehicle.pm_interval_days, 70),
              'pm_due_date', vehicle.pm_due_date,
              'pm_days_remaining', CASE WHEN vehicle.pm_due_date IS NULL THEN NULL ELSE vehicle.pm_due_date - current_date END,
              'location_label', vehicle.last_location_label,
              'location_city', vehicle.last_location_city,
              'lat', vehicle.last_lat,
              'lng', vehicle.last_lng,
              'speed_mph', vehicle.last_speed_mph,
              'heading', vehicle.last_heading,
              'status_override', vehicle.status_override,
              'active_warning_lights', vehicle.active_warning_lights
            ),
            urgent.payload,
            pm.payload,
            coalesce(open_work_orders.count, 0),
            coalesce(open_incidents.count, 0),
            now()
          FROM vehicles vehicle
          JOIN customers customer ON customer.id = vehicle.customer_id
          LEFT JOIN LATERAL (
            SELECT jsonb_build_object(
              'id', repair_order.id,
              'order_number', repair_order.order_number,
              'status', repair_order.status::text,
              'description', repair_order.description,
              'assigned_mechanic_id', repair_order.assigned_mechanic_id,
              'is_pm', repair_order.is_pm,
              'awaiting_parts', coalesce(repair_order.hold_reason ILIKE '%part%', false),
              'work_started_at', repair_order.work_started_at
            ) AS payload
            FROM repair_orders repair_order
            WHERE repair_order.vehicle_id = vehicle.id
              AND repair_order.is_internal
              AND repair_order.deleted_at IS NULL
              AND repair_order.status::text NOT IN ('completed', 'invoiced', 'paid', 'cancelled', 'declined')
            ORDER BY
              CASE WHEN repair_order.hold_reason ILIKE '%part%' THEN 0 ELSE 1 END,
              CASE repair_order.status::text
                WHEN 'in_progress' THEN 0 WHEN 'pending_review' THEN 1
                WHEN 'acknowledged' THEN 2 WHEN 'assigned' THEN 3
                WHEN 'approved' THEN 4 WHEN 'quoted' THEN 5 WHEN 'draft' THEN 6 ELSE 9
              END,
              repair_order.created_at DESC
            LIMIT 1
          ) urgent ON true
          LEFT JOIN LATERAL (
            SELECT jsonb_build_object(
              'id', repair_order.id,
              'order_number', repair_order.order_number,
              'status', repair_order.status::text,
              'description', repair_order.description,
              'assigned_mechanic_id', repair_order.assigned_mechanic_id,
              'is_pm', repair_order.is_pm,
              'awaiting_parts', coalesce(repair_order.hold_reason ILIKE '%part%', false),
              'work_started_at', repair_order.work_started_at
            ) AS payload
            FROM repair_orders repair_order
            WHERE repair_order.vehicle_id = vehicle.id
              AND repair_order.is_internal
              AND repair_order.is_pm
              AND repair_order.deleted_at IS NULL
              AND repair_order.status::text NOT IN ('completed', 'invoiced', 'paid', 'cancelled', 'declined')
            ORDER BY
              CASE WHEN repair_order.hold_reason ILIKE '%part%' THEN 0 ELSE 1 END,
              CASE repair_order.status::text
                WHEN 'in_progress' THEN 0 WHEN 'pending_review' THEN 1
                WHEN 'acknowledged' THEN 2 WHEN 'assigned' THEN 3
                WHEN 'approved' THEN 4 WHEN 'quoted' THEN 5 WHEN 'draft' THEN 6 ELSE 9
              END,
              repair_order.created_at DESC
            LIMIT 1
          ) pm ON true
          LEFT JOIN LATERAL (
            SELECT count(*)::integer AS count
            FROM repair_orders repair_order
            WHERE repair_order.vehicle_id = vehicle.id
              AND repair_order.is_internal
              AND repair_order.deleted_at IS NULL
              AND repair_order.status::text NOT IN ('completed', 'invoiced', 'paid', 'cancelled', 'declined')
          ) open_work_orders ON true
          LEFT JOIN LATERAL (
            SELECT count(*)::integer AS count
            FROM fleet_incidents incident
            WHERE incident.vehicle_id = vehicle.id AND incident.status::text <> 'resolved'
          ) open_incidents ON true
          WHERE vehicle.id = target_vehicle_id
            AND vehicle.deleted_at IS NULL
            AND customer.deleted_at IS NULL
            AND customer.is_internal_fleet;
        END;
        $$
    """


def upgrade() -> None:
    op.execute(_refresh_function(include_driver_phone=True))
    op.execute(
        """
        SELECT refresh_fleet_board_read_model(vehicle.id)
        FROM vehicles vehicle
        JOIN customers customer ON customer.id = vehicle.customer_id
        WHERE vehicle.deleted_at IS NULL
          AND customer.deleted_at IS NULL
          AND customer.is_internal_fleet
        """
    )


def downgrade() -> None:
    op.execute(_refresh_function(include_driver_phone=False))
    op.execute(
        """
        UPDATE fleet_board_read_models
        SET vehicle_data = vehicle_data - 'driver_phone'
        """
    )

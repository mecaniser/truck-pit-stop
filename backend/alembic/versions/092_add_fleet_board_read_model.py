"""add transactionally maintained fleet board read model

Revision ID: 092_fleet_board_read_model
Revises: 091
"""
from alembic import op
import sqlalchemy as sa


revision = "092_fleet_board_read_model"
down_revision = "091"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fleet_board_read_models",
        sa.Column("vehicle_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("vehicle_data", sa.dialects.postgresql.JSONB(), nullable=False),
        sa.Column("urgent_work_order", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("pm_work_order", sa.dialects.postgresql.JSONB(), nullable=True),
        sa.Column("open_work_order_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("open_incident_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("refreshed_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("vehicle_id"),
    )
    op.create_index("ix_fleet_board_read_models_tenant_id", "fleet_board_read_models", ["tenant_id"])
    op.execute(
        "CREATE INDEX ix_repair_orders_fleet_board_open "
        "ON repair_orders (vehicle_id, created_at DESC) "
        "WHERE is_internal AND deleted_at IS NULL"
    )
    op.execute(
        "CREATE INDEX ix_fleet_incidents_fleet_board_open "
        "ON fleet_incidents (vehicle_id) WHERE status::text <> 'resolved'"
    )

    # One recomputation function is shared by all fleet writers, including
    # imports. The board stores state, not presentation strings, so changing a
    # mechanic's or service's name cannot make a card stale.
    op.execute(
        """
        CREATE FUNCTION refresh_fleet_board_read_model(target_vehicle_id uuid)
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
              'mileage', vehicle.mileage,
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
    )
    op.execute(
        """
        CREATE FUNCTION refresh_fleet_board_read_model_from_vehicle()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM refresh_fleet_board_read_model(CASE WHEN TG_OP = 'DELETE' THEN OLD.id ELSE NEW.id END);
          RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION refresh_fleet_board_read_model_from_repair_order()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM refresh_fleet_board_read_model(CASE WHEN TG_OP = 'DELETE' THEN OLD.vehicle_id ELSE NEW.vehicle_id END);
          IF TG_OP = 'UPDATE' AND OLD.vehicle_id IS DISTINCT FROM NEW.vehicle_id THEN
            PERFORM refresh_fleet_board_read_model(OLD.vehicle_id);
          END IF;
          RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION refresh_fleet_board_read_model_from_incident()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
          PERFORM refresh_fleet_board_read_model(CASE WHEN TG_OP = 'DELETE' THEN OLD.vehicle_id ELSE NEW.vehicle_id END);
          IF TG_OP = 'UPDATE' AND OLD.vehicle_id IS DISTINCT FROM NEW.vehicle_id THEN
            PERFORM refresh_fleet_board_read_model(OLD.vehicle_id);
          END IF;
          RETURN NULL;
        END;
        $$
        """
    )
    op.execute(
        """
        CREATE FUNCTION refresh_fleet_board_read_model_from_customer()
        RETURNS trigger LANGUAGE plpgsql AS $$
        DECLARE vehicle_row record;
        BEGIN
          FOR vehicle_row IN SELECT id FROM vehicles WHERE customer_id = CASE WHEN TG_OP = 'DELETE' THEN OLD.id ELSE NEW.id END LOOP
            PERFORM refresh_fleet_board_read_model(vehicle_row.id);
          END LOOP;
          RETURN NULL;
        END;
        $$
        """
    )
    op.execute("CREATE TRIGGER fleet_board_read_model_vehicle AFTER INSERT OR UPDATE OR DELETE ON vehicles FOR EACH ROW EXECUTE FUNCTION refresh_fleet_board_read_model_from_vehicle()")
    op.execute("CREATE TRIGGER fleet_board_read_model_repair_order AFTER INSERT OR UPDATE OR DELETE ON repair_orders FOR EACH ROW EXECUTE FUNCTION refresh_fleet_board_read_model_from_repair_order()")
    op.execute("CREATE TRIGGER fleet_board_read_model_incident AFTER INSERT OR UPDATE OR DELETE ON fleet_incidents FOR EACH ROW EXECUTE FUNCTION refresh_fleet_board_read_model_from_incident()")
    op.execute("CREATE TRIGGER fleet_board_read_model_customer AFTER UPDATE OF is_internal_fleet, deleted_at ON customers FOR EACH ROW EXECUTE FUNCTION refresh_fleet_board_read_model_from_customer()")
    op.execute("SELECT refresh_fleet_board_read_model(id) FROM vehicles")


def downgrade() -> None:
    for trigger, table in (
        ("fleet_board_read_model_customer", "customers"),
        ("fleet_board_read_model_incident", "fleet_incidents"),
        ("fleet_board_read_model_repair_order", "repair_orders"),
        ("fleet_board_read_model_vehicle", "vehicles"),
    ):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger} ON {table}")
    for function in (
        "refresh_fleet_board_read_model_from_customer()",
        "refresh_fleet_board_read_model_from_incident()",
        "refresh_fleet_board_read_model_from_repair_order()",
        "refresh_fleet_board_read_model_from_vehicle()",
        "refresh_fleet_board_read_model(uuid)",
    ):
        op.execute(f"DROP FUNCTION IF EXISTS {function}")
    op.execute("DROP INDEX IF EXISTS ix_fleet_incidents_fleet_board_open")
    op.execute("DROP INDEX IF EXISTS ix_repair_orders_fleet_board_open")
    op.drop_index("ix_fleet_board_read_models_tenant_id", table_name="fleet_board_read_models")
    op.drop_table("fleet_board_read_models")

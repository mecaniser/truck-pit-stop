"""add fleet board fields: vehicle driver/PM/telematics, RO is_pm, parts warranty

Revision ID: 049
Revises: 048
Create Date: 2026-06-16
"""
from alembic import op
import sqlalchemy as sa


revision = "049"
down_revision = "048"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Vehicle: driver + mileage-based PM + last-known telematics location
    op.add_column("vehicles", sa.Column("driver_name", sa.String(length=160), nullable=True))
    op.add_column("vehicles", sa.Column("driver_phone", sa.String(length=20), nullable=True))
    op.add_column("vehicles", sa.Column("pm_interval_miles", sa.Integer(), nullable=False, server_default="25000"))
    op.add_column("vehicles", sa.Column("next_pm_miles", sa.Integer(), nullable=True))
    op.add_column("vehicles", sa.Column("telematics_device_id", sa.String(length=120), nullable=True))
    op.add_column("vehicles", sa.Column("last_lat", sa.Float(), nullable=True))
    op.add_column("vehicles", sa.Column("last_lng", sa.Float(), nullable=True))
    op.add_column("vehicles", sa.Column("last_location_label", sa.String(length=200), nullable=True))
    op.add_column("vehicles", sa.Column("last_location_city", sa.String(length=120), nullable=True))
    op.add_column("vehicles", sa.Column("last_speed_mph", sa.Integer(), nullable=True))
    op.add_column("vehicles", sa.Column("last_heading", sa.String(length=8), nullable=True))
    op.add_column("vehicles", sa.Column("last_location_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_vehicles_telematics_device_id", "vehicles", ["telematics_device_id"])
    op.alter_column("vehicles", "pm_interval_miles", server_default=None)

    # RepairOrder: preventive-maintenance flag
    op.add_column("repair_orders", sa.Column("is_pm", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.create_index("ix_repair_orders_is_pm", "repair_orders", ["is_pm"])
    op.alter_column("repair_orders", "is_pm", server_default=None)

    # PartsUsage: warranty tracking
    op.add_column("parts_usage", sa.Column("warranty_until", sa.Date(), nullable=True))
    op.add_column("parts_usage", sa.Column("warranty_miles", sa.Integer(), nullable=True))


def downgrade() -> None:
    op.drop_column("parts_usage", "warranty_miles")
    op.drop_column("parts_usage", "warranty_until")
    op.drop_index("ix_repair_orders_is_pm", table_name="repair_orders")
    op.drop_column("repair_orders", "is_pm")
    op.drop_index("ix_vehicles_telematics_device_id", table_name="vehicles")
    for col in (
        "last_location_at", "last_heading", "last_speed_mph", "last_location_city",
        "last_location_label", "last_lng", "last_lat", "telematics_device_id",
        "next_pm_miles", "pm_interval_miles", "driver_phone", "driver_name",
    ):
        op.drop_column("vehicles", col)

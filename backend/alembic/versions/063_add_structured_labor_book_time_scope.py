"""add structured labor book time scope fields

Revision ID: 063
Revises: 062
"""
from alembic import op
import sqlalchemy as sa


revision = "063"
down_revision = "062"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("labor_operation_memory", sa.Column("vehicle_year", sa.Integer(), nullable=True))
    op.add_column("labor_operation_memory", sa.Column("vehicle_make", sa.String(length=100), nullable=True))
    op.add_column("labor_operation_memory", sa.Column("vehicle_model", sa.String(length=100), nullable=True))
    op.add_column("labor_operation_memory", sa.Column("vehicle_type", sa.String(length=100), nullable=True))
    op.add_column("labor_operation_memory", sa.Column("body_class", sa.String(length=150), nullable=True))
    op.add_column("labor_operation_memory", sa.Column("engine", sa.String(length=150), nullable=True))
    op.add_column("labor_operation_memory", sa.Column("fuel_type", sa.String(length=100), nullable=True))
    op.add_column("labor_operation_memory", sa.Column("engine_cylinders", sa.Integer(), nullable=True))
    op.add_column("labor_operation_memory", sa.Column("engine_displacement_l", sa.Float(), nullable=True))
    op.add_column("labor_operation_memory", sa.Column("gvwr", sa.String(length=100), nullable=True))
    op.add_column("labor_operation_memory", sa.Column("vin_sample", sa.String(length=17), nullable=True))
    op.create_index(op.f("ix_labor_operation_memory_vehicle_year"), "labor_operation_memory", ["vehicle_year"], unique=False)
    op.create_index(op.f("ix_labor_operation_memory_vehicle_make"), "labor_operation_memory", ["vehicle_make"], unique=False)
    op.create_index(op.f("ix_labor_operation_memory_vehicle_model"), "labor_operation_memory", ["vehicle_model"], unique=False)
    op.create_index(op.f("ix_labor_operation_memory_engine"), "labor_operation_memory", ["engine"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_labor_operation_memory_engine"), table_name="labor_operation_memory")
    op.drop_index(op.f("ix_labor_operation_memory_vehicle_model"), table_name="labor_operation_memory")
    op.drop_index(op.f("ix_labor_operation_memory_vehicle_make"), table_name="labor_operation_memory")
    op.drop_index(op.f("ix_labor_operation_memory_vehicle_year"), table_name="labor_operation_memory")
    op.drop_column("labor_operation_memory", "vin_sample")
    op.drop_column("labor_operation_memory", "gvwr")
    op.drop_column("labor_operation_memory", "engine_displacement_l")
    op.drop_column("labor_operation_memory", "engine_cylinders")
    op.drop_column("labor_operation_memory", "fuel_type")
    op.drop_column("labor_operation_memory", "engine")
    op.drop_column("labor_operation_memory", "body_class")
    op.drop_column("labor_operation_memory", "vehicle_type")
    op.drop_column("labor_operation_memory", "vehicle_model")
    op.drop_column("labor_operation_memory", "vehicle_make")
    op.drop_column("labor_operation_memory", "vehicle_year")

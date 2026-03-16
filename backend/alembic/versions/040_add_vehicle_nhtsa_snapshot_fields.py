"""add vehicle nhtsa snapshot fields

Revision ID: 040
Revises: 039
"""
from alembic import op
import sqlalchemy as sa


revision = "040"
down_revision = "039"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("vehicles", sa.Column("nhtsa_make", sa.String(length=100), nullable=True))
    op.add_column("vehicles", sa.Column("nhtsa_model", sa.String(length=100), nullable=True))
    op.add_column("vehicles", sa.Column("nhtsa_model_year", sa.Integer(), nullable=True))
    op.add_column("vehicles", sa.Column("nhtsa_vehicle_type", sa.String(length=100), nullable=True))
    op.add_column("vehicles", sa.Column("nhtsa_body_class", sa.String(length=150), nullable=True))
    op.add_column("vehicles", sa.Column("nhtsa_drive_type", sa.String(length=100), nullable=True))
    op.add_column("vehicles", sa.Column("nhtsa_fuel_type", sa.String(length=100), nullable=True))
    op.add_column("vehicles", sa.Column("nhtsa_engine_cylinders", sa.Integer(), nullable=True))
    op.add_column("vehicles", sa.Column("nhtsa_engine_displacement_l", sa.Float(), nullable=True))
    op.add_column("vehicles", sa.Column("nhtsa_engine_hp", sa.Integer(), nullable=True))
    op.add_column("vehicles", sa.Column("nhtsa_transmission", sa.String(length=100), nullable=True))
    op.add_column("vehicles", sa.Column("nhtsa_gvwr", sa.String(length=100), nullable=True))
    op.add_column("vehicles", sa.Column("nhtsa_decoded_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("vehicles", "nhtsa_decoded_at")
    op.drop_column("vehicles", "nhtsa_gvwr")
    op.drop_column("vehicles", "nhtsa_transmission")
    op.drop_column("vehicles", "nhtsa_engine_hp")
    op.drop_column("vehicles", "nhtsa_engine_displacement_l")
    op.drop_column("vehicles", "nhtsa_engine_cylinders")
    op.drop_column("vehicles", "nhtsa_fuel_type")
    op.drop_column("vehicles", "nhtsa_drive_type")
    op.drop_column("vehicles", "nhtsa_body_class")
    op.drop_column("vehicles", "nhtsa_vehicle_type")
    op.drop_column("vehicles", "nhtsa_model_year")
    op.drop_column("vehicles", "nhtsa_model")
    op.drop_column("vehicles", "nhtsa_make")

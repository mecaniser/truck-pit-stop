"""add_services_appointments

Revision ID: 002
Revises: 001
Create Date: 2025-12-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '002'
down_revision: Union[str, None] = '001'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Define enum
appointmentstatus = postgresql.ENUM(
    'pending', 'confirmed', 'in_progress', 'completed', 'cancelled', 'no_show',
    name='appointmentstatus', create_type=False
)


def upgrade() -> None:
    # Create enum type
    appointmentstatus.create(op.get_bind(), checkfirst=True)

    # 1. Create service_categories table
    op.create_table('service_categories',
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('name', sa.String(length=100), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('icon', sa.String(length=50), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_service_categories_id', 'service_categories', ['id'], unique=False)
    op.create_index('ix_service_categories_tenant_id', 'service_categories', ['tenant_id'], unique=False)

    # 2. Create services table
    op.create_table('services',
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('category_id', sa.UUID(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('duration_minutes', sa.Integer(), nullable=False, server_default='60'),
        sa.Column('base_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('requires_vehicle', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('icon', sa.String(length=50), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['category_id'], ['service_categories.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_services_id', 'services', ['id'], unique=False)
    op.create_index('ix_services_tenant_id', 'services', ['tenant_id'], unique=False)
    op.create_index('ix_services_category_id', 'services', ['category_id'], unique=False)

    # 3. Create appointments table
    op.create_table('appointments',
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('customer_id', sa.UUID(), nullable=False),
        sa.Column('vehicle_id', sa.UUID(), nullable=True),
        sa.Column('service_id', sa.UUID(), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('duration_minutes', sa.Integer(), nullable=False),
        sa.Column('status', appointmentstatus, nullable=False, server_default='pending'),
        sa.Column('price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('stripe_payment_intent_id', sa.String(length=255), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('customer_notes', sa.Text(), nullable=True),
        sa.Column('internal_notes', sa.Text(), nullable=True),
        sa.Column('confirmation_number', sa.String(length=20), nullable=False),
        sa.Column('repair_order_id', sa.UUID(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id']),
        sa.ForeignKeyConstraint(['repair_order_id'], ['repair_orders.id']),
        sa.ForeignKeyConstraint(['service_id'], ['services.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_appointments_id', 'appointments', ['id'], unique=False)
    op.create_index('ix_appointments_tenant_id', 'appointments', ['tenant_id'], unique=False)
    op.create_index('ix_appointments_customer_id', 'appointments', ['customer_id'], unique=False)
    op.create_index('ix_appointments_service_id', 'appointments', ['service_id'], unique=False)
    op.create_index('ix_appointments_scheduled_at', 'appointments', ['scheduled_at'], unique=False)
    op.create_index('ix_appointments_status', 'appointments', ['status'], unique=False)
    op.create_index('ix_appointments_confirmation_number', 'appointments', ['confirmation_number'], unique=True)
    op.create_index('ix_appointments_stripe_payment_intent_id', 'appointments', ['stripe_payment_intent_id'], unique=True)


def downgrade() -> None:
    op.drop_table('appointments')
    op.drop_table('services')
    op.drop_table('service_categories')
    
    # Drop enum type
    appointmentstatus.drop(op.get_bind(), checkfirst=True)

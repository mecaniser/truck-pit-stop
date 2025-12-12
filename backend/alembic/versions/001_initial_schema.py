"""initial_schema

Revision ID: 001
Revises: 
Create Date: 2025-12-11

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '001'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Define enums as module-level objects (values must match Python enum .value)
userrole = postgresql.ENUM('super_admin', 'garage_admin', 'mechanic', 'receptionist', 'customer', name='userrole', create_type=False)
repairorderstatus = postgresql.ENUM('draft', 'quoted', 'approved', 'in_progress', 'completed', 'invoiced', 'paid', 'cancelled', name='repairorderstatus', create_type=False)
invoicestatus = postgresql.ENUM('draft', 'sent', 'paid', 'overdue', 'cancelled', name='invoicestatus', create_type=False)
paymentmethod = postgresql.ENUM('stripe', 'cash', 'check', 'ach', 'other', name='paymentmethod', create_type=False)
paymentstatus = postgresql.ENUM('pending', 'completed', 'failed', 'refunded', name='paymentstatus', create_type=False)
notificationtype = postgresql.ENUM('email', 'sms', name='notificationtype', create_type=False)
notificationstatus = postgresql.ENUM('pending', 'sent', 'failed', 'delivered', name='notificationstatus', create_type=False)


def upgrade() -> None:
    # Create enum types first
    userrole.create(op.get_bind(), checkfirst=True)
    repairorderstatus.create(op.get_bind(), checkfirst=True)
    invoicestatus.create(op.get_bind(), checkfirst=True)
    paymentmethod.create(op.get_bind(), checkfirst=True)
    paymentstatus.create(op.get_bind(), checkfirst=True)
    notificationtype.create(op.get_bind(), checkfirst=True)
    notificationstatus.create(op.get_bind(), checkfirst=True)

    # 1. Create base tables (no FK dependencies)
    op.create_table('tenants',
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('slug', sa.String(length=100), nullable=False),
        sa.Column('address', sa.String(length=500), nullable=True),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_tenants_id', 'tenants', ['id'], unique=False)
    op.create_index('ix_tenants_name', 'tenants', ['name'], unique=False)
    op.create_index('ix_tenants_slug', 'tenants', ['slug'], unique=True)

    # 2. Create tables that depend only on tenants
    op.create_table('customers',
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('first_name', sa.String(length=100), nullable=False),
        sa.Column('last_name', sa.String(length=100), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('billing_address_line1', sa.String(length=255), nullable=True),
        sa.Column('billing_address_line2', sa.String(length=255), nullable=True),
        sa.Column('billing_city', sa.String(length=100), nullable=True),
        sa.Column('billing_state', sa.String(length=50), nullable=True),
        sa.Column('billing_zip', sa.String(length=20), nullable=True),
        sa.Column('billing_country', sa.String(length=100), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_customers_email', 'customers', ['email'], unique=False)
    op.create_index('ix_customers_id', 'customers', ['id'], unique=False)
    op.create_index('ix_customers_tenant_id', 'customers', ['tenant_id'], unique=False)

    op.create_table('inventory',
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('sku', sa.String(length=100), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('category', sa.String(length=100), nullable=True),
        sa.Column('stock_quantity', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('reorder_level', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('cost', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('selling_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('supplier_name', sa.String(length=255), nullable=True),
        sa.Column('supplier_contact', sa.String(length=255), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_inventory_id', 'inventory', ['id'], unique=False)
    op.create_index('ix_inventory_sku', 'inventory', ['sku'], unique=False)
    op.create_index('ix_inventory_tenant_id', 'inventory', ['tenant_id'], unique=False)

    op.create_table('notifications',
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('type', notificationtype, nullable=False),
        sa.Column('status', notificationstatus, nullable=False),
        sa.Column('recipient_email', sa.String(length=255), nullable=True),
        sa.Column('recipient_phone', sa.String(length=20), nullable=True),
        sa.Column('subject', sa.String(length=255), nullable=True),
        sa.Column('body', sa.Text(), nullable=False),
        sa.Column('template_name', sa.String(length=100), nullable=True),
        sa.Column('external_id', sa.String(length=255), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('sent_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('delivered_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_notifications_id', 'notifications', ['id'], unique=False)
    op.create_index('ix_notifications_recipient_email', 'notifications', ['recipient_email'], unique=False)
    op.create_index('ix_notifications_recipient_phone', 'notifications', ['recipient_phone'], unique=False)
    op.create_index('ix_notifications_status', 'notifications', ['status'], unique=False)
    op.create_index('ix_notifications_tenant_id', 'notifications', ['tenant_id'], unique=False)
    op.create_index('ix_notifications_type', 'notifications', ['type'], unique=False)

    # 3. Create vehicles (depends on tenants and customers)
    op.create_table('vehicles',
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('customer_id', sa.UUID(), nullable=False),
        sa.Column('vin', sa.String(length=17), nullable=True),
        sa.Column('make', sa.String(length=100), nullable=False),
        sa.Column('model', sa.String(length=100), nullable=False),
        sa.Column('year', sa.Integer(), nullable=True),
        sa.Column('license_plate', sa.String(length=20), nullable=True),
        sa.Column('color', sa.String(length=50), nullable=True),
        sa.Column('mileage', sa.Integer(), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_vehicles_customer_id', 'vehicles', ['customer_id'], unique=False)
    op.create_index('ix_vehicles_id', 'vehicles', ['id'], unique=False)
    op.create_index('ix_vehicles_license_plate', 'vehicles', ['license_plate'], unique=False)
    op.create_index('ix_vehicles_tenant_id', 'vehicles', ['tenant_id'], unique=False)
    op.create_index('ix_vehicles_vin', 'vehicles', ['vin'], unique=False)

    # 4. Create users (depends on tenants, customers)
    op.create_table('users',
        sa.Column('email', sa.String(length=255), nullable=False),
        sa.Column('hashed_password', sa.String(length=255), nullable=False),
        sa.Column('full_name', sa.String(length=255), nullable=True),
        sa.Column('phone', sa.String(length=20), nullable=True),
        sa.Column('role', userrole, nullable=False),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('is_verified', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('tenant_id', sa.UUID(), nullable=True),
        sa.Column('customer_id', sa.UUID(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('customer_id')
    )
    op.create_index('ix_users_email', 'users', ['email'], unique=True)
    op.create_index('ix_users_id', 'users', ['id'], unique=False)
    op.create_index('ix_users_tenant_id', 'users', ['tenant_id'], unique=False)

    # 5. Create repair_orders
    op.create_table('repair_orders',
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('customer_id', sa.UUID(), nullable=False),
        sa.Column('vehicle_id', sa.UUID(), nullable=False),
        sa.Column('order_number', sa.String(length=50), nullable=False),
        sa.Column('status', repairorderstatus, nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('customer_notes', sa.Text(), nullable=True),
        sa.Column('internal_notes', sa.Text(), nullable=True),
        sa.Column('assigned_mechanic_id', sa.UUID(), nullable=True),
        sa.Column('total_parts_cost', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0.00'),
        sa.Column('total_labor_cost', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0.00'),
        sa.Column('total_cost', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0.00'),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['assigned_mechanic_id'], ['users.id']),
        sa.ForeignKeyConstraint(['customer_id'], ['customers.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.ForeignKeyConstraint(['vehicle_id'], ['vehicles.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_repair_orders_customer_id', 'repair_orders', ['customer_id'], unique=False)
    op.create_index('ix_repair_orders_id', 'repair_orders', ['id'], unique=False)
    op.create_index('ix_repair_orders_order_number', 'repair_orders', ['order_number'], unique=True)
    op.create_index('ix_repair_orders_status', 'repair_orders', ['status'], unique=False)
    op.create_index('ix_repair_orders_tenant_id', 'repair_orders', ['tenant_id'], unique=False)
    op.create_index('ix_repair_orders_vehicle_id', 'repair_orders', ['vehicle_id'], unique=False)

    # 6. Create quotes (now repair_orders exists)
    op.create_table('quotes',
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('repair_order_id', sa.UUID(), nullable=False),
        sa.Column('quote_number', sa.String(length=50), nullable=False),
        sa.Column('total_amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_approved', sa.Boolean(), nullable=False, server_default='false'),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['repair_order_id'], ['repair_orders.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('repair_order_id')
    )
    op.create_index('ix_quotes_id', 'quotes', ['id'], unique=False)
    op.create_index('ix_quotes_quote_number', 'quotes', ['quote_number'], unique=True)
    op.create_index('ix_quotes_tenant_id', 'quotes', ['tenant_id'], unique=False)

    # 7. Create invoices (now repair_orders exists)
    op.create_table('invoices',
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('repair_order_id', sa.UUID(), nullable=False),
        sa.Column('invoice_number', sa.String(length=50), nullable=False),
        sa.Column('status', invoicestatus, nullable=False),
        sa.Column('subtotal', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('tax_amount', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0.00'),
        sa.Column('discount_amount', sa.Numeric(precision=10, scale=2), nullable=False, server_default='0.00'),
        sa.Column('total_amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('due_date', sa.DateTime(timezone=True), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['repair_order_id'], ['repair_orders.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('repair_order_id')
    )
    op.create_index('ix_invoices_id', 'invoices', ['id'], unique=False)
    op.create_index('ix_invoices_invoice_number', 'invoices', ['invoice_number'], unique=True)
    op.create_index('ix_invoices_status', 'invoices', ['status'], unique=False)
    op.create_index('ix_invoices_tenant_id', 'invoices', ['tenant_id'], unique=False)

    # 8. Create payments (depends on invoices)
    op.create_table('payments',
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('invoice_id', sa.UUID(), nullable=False),
        sa.Column('payment_number', sa.String(length=50), nullable=False),
        sa.Column('amount', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('method', paymentmethod, nullable=False),
        sa.Column('status', paymentstatus, nullable=False),
        sa.Column('stripe_payment_intent_id', sa.String(length=255), nullable=True),
        sa.Column('stripe_charge_id', sa.String(length=255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('receipt_url', sa.String(length=500), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['invoice_id'], ['invoices.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_payments_id', 'payments', ['id'], unique=False)
    op.create_index('ix_payments_invoice_id', 'payments', ['invoice_id'], unique=False)
    op.create_index('ix_payments_payment_number', 'payments', ['payment_number'], unique=True)
    op.create_index('ix_payments_status', 'payments', ['status'], unique=False)
    op.create_index('ix_payments_stripe_payment_intent_id', 'payments', ['stripe_payment_intent_id'], unique=True)
    op.create_index('ix_payments_tenant_id', 'payments', ['tenant_id'], unique=False)

    # 9. Create parts_usage (depends on repair_orders and inventory)
    op.create_table('parts_usage',
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('repair_order_id', sa.UUID(), nullable=False),
        sa.Column('inventory_id', sa.UUID(), nullable=False),
        sa.Column('quantity', sa.Integer(), nullable=False),
        sa.Column('unit_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('total_price', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['inventory_id'], ['inventory.id']),
        sa.ForeignKeyConstraint(['repair_order_id'], ['repair_orders.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_parts_usage_id', 'parts_usage', ['id'], unique=False)
    op.create_index('ix_parts_usage_inventory_id', 'parts_usage', ['inventory_id'], unique=False)
    op.create_index('ix_parts_usage_repair_order_id', 'parts_usage', ['repair_order_id'], unique=False)
    op.create_index('ix_parts_usage_tenant_id', 'parts_usage', ['tenant_id'], unique=False)

    # 10. Create labor (depends on repair_orders and users)
    op.create_table('labor',
        sa.Column('tenant_id', sa.UUID(), nullable=False),
        sa.Column('repair_order_id', sa.UUID(), nullable=False),
        sa.Column('service_code', sa.String(length=50), nullable=True),
        sa.Column('description', sa.Text(), nullable=False),
        sa.Column('hours', sa.Numeric(precision=5, scale=2), nullable=False),
        sa.Column('hourly_rate', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('total_cost', sa.Numeric(precision=10, scale=2), nullable=False),
        sa.Column('mechanic_id', sa.UUID(), nullable=True),
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('deleted_at', sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(['mechanic_id'], ['users.id']),
        sa.ForeignKeyConstraint(['repair_order_id'], ['repair_orders.id']),
        sa.ForeignKeyConstraint(['tenant_id'], ['tenants.id']),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_labor_id', 'labor', ['id'], unique=False)
    op.create_index('ix_labor_repair_order_id', 'labor', ['repair_order_id'], unique=False)
    op.create_index('ix_labor_tenant_id', 'labor', ['tenant_id'], unique=False)


def downgrade() -> None:
    op.drop_table('labor')
    op.drop_table('parts_usage')
    op.drop_table('payments')
    op.drop_table('invoices')
    op.drop_table('quotes')
    op.drop_table('repair_orders')
    op.drop_table('users')
    op.drop_table('vehicles')
    op.drop_table('notifications')
    op.drop_table('inventory')
    op.drop_table('customers')
    op.drop_table('tenants')
    
    # Drop enum types
    notificationstatus.drop(op.get_bind(), checkfirst=True)
    notificationtype.drop(op.get_bind(), checkfirst=True)
    paymentstatus.drop(op.get_bind(), checkfirst=True)
    paymentmethod.drop(op.get_bind(), checkfirst=True)
    invoicestatus.drop(op.get_bind(), checkfirst=True)
    repairorderstatus.drop(op.get_bind(), checkfirst=True)
    userrole.drop(op.get_bind(), checkfirst=True)

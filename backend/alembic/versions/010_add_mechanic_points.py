"""Add mechanic points tables

Revision ID: 010
Revises: 009
Create Date: 2026-01-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "010"
down_revision = "009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum type if not exists
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE pointstransactiontype AS ENUM ('earned', 'redeemed_pto', 'redeemed_cash', 'bonus', 'adjustment');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Create mechanic_points table using raw SQL to avoid SQLAlchemy enum issues
    op.execute("""
        CREATE TABLE IF NOT EXISTS mechanic_points (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id),
            mechanic_id UUID NOT NULL REFERENCES users(id),
            transaction_type pointstransactiontype NOT NULL,
            points INTEGER NOT NULL,
            repair_order_id UUID REFERENCES repair_orders(id),
            labor_value NUMERIC(10, 2),
            multiplier NUMERIC(3, 2) NOT NULL DEFAULT 1.00,
            notes TEXT,
            redemption_value NUMERIC(10, 2),
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            deleted_at TIMESTAMP WITH TIME ZONE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_mechanic_points_tenant_id ON mechanic_points(tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mechanic_points_mechanic_id ON mechanic_points(mechanic_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mechanic_points_transaction_type ON mechanic_points(transaction_type)")
    
    # Create mechanic_points_balance table
    op.execute("""
        CREATE TABLE IF NOT EXISTS mechanic_points_balance (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id),
            mechanic_id UUID NOT NULL UNIQUE REFERENCES users(id),
            available_points INTEGER NOT NULL DEFAULT 0,
            total_earned INTEGER NOT NULL DEFAULT 0,
            total_redeemed INTEGER NOT NULL DEFAULT 0,
            current_streak_days INTEGER NOT NULL DEFAULT 0,
            last_work_date TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            deleted_at TIMESTAMP WITH TIME ZONE
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_mechanic_points_balance_tenant_id ON mechanic_points_balance(tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_mechanic_points_balance_mechanic_id ON mechanic_points_balance(mechanic_id)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS mechanic_points_balance")
    op.execute("DROP TABLE IF EXISTS mechanic_points")
    op.execute("DROP TYPE IF EXISTS pointstransactiontype")

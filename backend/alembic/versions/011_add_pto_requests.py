"""Add PTO requests table

Revision ID: 011
Revises: 010
Create Date: 2026-01-29
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "011"
down_revision = "010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Create enum types
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE ptorequeststatus AS ENUM ('pending', 'approved', 'denied', 'cancelled');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE ptorequesttype AS ENUM ('pto', 'cash');
        EXCEPTION
            WHEN duplicate_object THEN null;
        END $$;
    """)
    
    # Create pto_requests table
    op.execute("""
        CREATE TABLE IF NOT EXISTS pto_requests (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            tenant_id UUID NOT NULL REFERENCES tenants(id),
            mechanic_id UUID NOT NULL REFERENCES users(id),
            request_type ptorequesttype NOT NULL,
            status ptorequeststatus NOT NULL DEFAULT 'pending',
            pto_start_date DATE,
            pto_end_date DATE,
            pto_days INTEGER,
            points_requested INTEGER NOT NULL,
            cash_value INTEGER,
            mechanic_notes TEXT,
            manager_notes TEXT,
            processed_by_id UUID REFERENCES users(id),
            processed_at TIMESTAMP WITH TIME ZONE,
            created_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW(),
            updated_at TIMESTAMP WITH TIME ZONE NOT NULL DEFAULT NOW()
        )
    """)
    op.execute("CREATE INDEX IF NOT EXISTS ix_pto_requests_tenant_id ON pto_requests(tenant_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pto_requests_mechanic_id ON pto_requests(mechanic_id)")
    op.execute("CREATE INDEX IF NOT EXISTS ix_pto_requests_status ON pto_requests(status)")


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS pto_requests")
    op.execute("DROP TYPE IF EXISTS ptorequeststatus")
    op.execute("DROP TYPE IF EXISTS ptorequesttype")

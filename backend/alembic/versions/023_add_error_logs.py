"""Add error_logs table for persistent error tracking

Revision ID: 023
Revises: 022
Create Date: 2026-02-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB


revision = "023"
down_revision = "022"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "error_logs",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), onupdate=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        
        # Request tracking
        sa.Column("correlation_id", sa.String(255), nullable=True, index=True),
        
        # Error classification
        sa.Column("error_type", sa.String(255), nullable=False, index=True),
        sa.Column("error_category", sa.String(50), nullable=False, index=True),
        sa.Column("severity", sa.String(20), nullable=False),
        
        # Request context
        sa.Column("endpoint", sa.String(500), nullable=True, index=True),
        sa.Column("method", sa.String(10), nullable=True),
        sa.Column("status_code", sa.Integer(), nullable=True, index=True),
        
        # User context
        sa.Column("user_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id", ondelete="SET NULL"), nullable=True, index=True),
        
        # Error details
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("stack_trace", sa.Text(), nullable=True),
        sa.Column("request_context", JSONB(), nullable=True),
        
        # Resolution tracking
        sa.Column("resolved", sa.Boolean(), default=False, nullable=False, index=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_by_id", UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
    )
    
    # Create index for timestamp-based queries (most common)
    op.create_index("idx_error_logs_created_at", "error_logs", ["created_at"])


def downgrade() -> None:
    op.drop_index("idx_error_logs_created_at", table_name="error_logs")
    op.drop_table("error_logs")

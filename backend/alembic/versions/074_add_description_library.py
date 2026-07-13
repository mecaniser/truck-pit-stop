"""add description_library_entries table

Stores the AI-canonicalized version of a tenant's historical repair-order
descriptions (typos fixed, compound entries split, near-duplicates merged).
Populated in bulk by the description-library regeneration service; the fast
pg_trgm-backed /repair-orders/description-suggestions endpoint queries this
table first and falls back to raw RepairOrder.description history when a
tenant has never regenerated it.

Revision ID: 074
Revises: 073
Create Date: 2026-07-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "074"
down_revision = "073"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "description_library_entries",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("canonical_text", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.Column("source_count", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_regenerated_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_description_library_entries_tenant_id",
        "description_library_entries",
        ["tenant_id"],
    )
    op.execute(
        "CREATE INDEX ix_description_library_entries_canonical_text_trgm "
        "ON description_library_entries USING gin (canonical_text gin_trgm_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_description_library_entries_canonical_text_trgm", table_name="description_library_entries")
    op.drop_index("ix_description_library_entries_tenant_id", table_name="description_library_entries")
    op.drop_table("description_library_entries")

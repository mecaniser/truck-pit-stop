"""add library_type to description_library_entries; rename source-agnostically

Generalizes the AI-canonicalized suggestion library beyond just repair-order
descriptions: the same table/mechanism now also holds canonicalized service
names, inventory part names, and inventory categories, one row set per
(tenant_id, library_type). Existing rows are backfilled to 'ro_description'
since that's the only source that existed before this migration.

Revision ID: 075
Revises: 074
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa


revision = "075"
down_revision = "074"
branch_labels = None
depends_on = None

LIBRARY_TYPES = ("ro_description", "service_name", "part_name", "part_category")


def upgrade() -> None:
    op.add_column(
        "description_library_entries",
        sa.Column("library_type", sa.String(length=30), nullable=False, server_default="ro_description"),
    )
    op.alter_column("description_library_entries", "library_type", server_default=None)

    # The old trigram index and tenant index don't include library_type — a
    # lookup for one type still has to scan all types' rows for that tenant.
    # Drop and recreate scoped to (tenant_id, library_type).
    op.drop_index("ix_description_library_entries_canonical_text_trgm", table_name="description_library_entries")
    op.drop_index("ix_description_library_entries_tenant_id", table_name="description_library_entries")
    op.create_index(
        "ix_description_library_entries_tenant_type",
        "description_library_entries",
        ["tenant_id", "library_type"],
    )
    op.execute(
        "CREATE INDEX ix_description_library_entries_canonical_text_trgm "
        "ON description_library_entries USING gin (canonical_text gin_trgm_ops)"
    )


def downgrade() -> None:
    op.drop_index("ix_description_library_entries_canonical_text_trgm", table_name="description_library_entries")
    op.drop_index("ix_description_library_entries_tenant_type", table_name="description_library_entries")
    op.create_index("ix_description_library_entries_tenant_id", "description_library_entries", ["tenant_id"])
    op.execute(
        "CREATE INDEX ix_description_library_entries_canonical_text_trgm "
        "ON description_library_entries USING gin (canonical_text gin_trgm_ops)"
    )
    op.drop_column("description_library_entries", "library_type")

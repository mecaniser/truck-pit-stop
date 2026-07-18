"""add parts_usage.source_line_id

Links a part directly to a labor line (labor.id) so parts can be attached to any
operation line, including free-form repair operations / manual lines that have no
source_service_id. Legacy service-bundled parts continue to correlate via
source_service_id; new per-operation attachments use source_line_id.

Revision ID: 081
Revises: 080
Create Date: 2026-07-18
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "081"
down_revision = "080"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "parts_usage",
        sa.Column("source_line_id", postgresql.UUID(as_uuid=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_parts_usage_source_line_id_labor",
        "parts_usage",
        "labor",
        ["source_line_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        op.f("ix_parts_usage_source_line_id"),
        "parts_usage",
        ["source_line_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f("ix_parts_usage_source_line_id"), table_name="parts_usage")
    op.drop_constraint("fk_parts_usage_source_line_id_labor", "parts_usage", type_="foreignkey")
    op.drop_column("parts_usage", "source_line_id")

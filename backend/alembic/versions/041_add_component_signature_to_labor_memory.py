"""add component_signature to labor_operation_memory

Revision ID: 041
Revises: 040
"""
from alembic import op
import sqlalchemy as sa


revision = "041"
down_revision = "040"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "labor_operation_memory",
        sa.Column("component_signature", sa.String(length=255), nullable=True),
    )
    op.create_index(
        op.f("ix_labor_operation_memory_component_signature"),
        "labor_operation_memory",
        ["component_signature"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_labor_operation_memory_component_signature"),
        table_name="labor_operation_memory",
    )
    op.drop_column("labor_operation_memory", "component_signature")

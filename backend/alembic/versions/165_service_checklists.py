"""Service template definitions and immutable work-order task evidence.

After adoption roll back application code while retaining this additive schema;
a downgrade destroys new checklist evidence.
"""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB, UUID

revision = "165_service_checklists"
down_revision = "164_motive_driver_journal"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "services",
        sa.Column(
            "checklist_template",
            JSONB(),
            nullable=False,
            server_default=sa.text("'[]'::jsonb"),
        ),
    )
    op.add_column(
        "services",
        sa.Column(
            "checklist_version", sa.Integer(), nullable=False, server_default="0"
        ),
    )
    op.create_table(
        "repair_order_checklist_items",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column(
            "tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False
        ),
        sa.Column(
            "repair_order_id",
            UUID(as_uuid=True),
            sa.ForeignKey("repair_orders.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "labor_id",
            UUID(as_uuid=True),
            sa.ForeignKey("labor.id", ondelete="SET NULL"),
        ),
        sa.Column("labor_id_snapshot", UUID(as_uuid=True), nullable=False),
        sa.Column("source_service_id_snapshot", UUID(as_uuid=True), nullable=False),
        sa.Column("source_template_item_id", UUID(as_uuid=True), nullable=False),
        sa.Column("source_template_version", sa.Integer(), nullable=False),
        sa.Column("service_name_snapshot", sa.String(255), nullable=False),
        sa.Column("label", sa.String(300), nullable=False),
        sa.Column("required", sa.Boolean(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column(
            "is_completed", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("completed_by_user_id", UUID(as_uuid=True)),
        sa.Column("completed_by_name", sa.String(255)),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("removed_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "labor_id", "source_template_item_id", name="uq_ro_checklist_labor_template"
        ),
        sa.CheckConstraint("position >= 0", name="ck_ro_checklist_position"),
        sa.CheckConstraint("version > 0", name="ck_ro_checklist_version"),
        sa.CheckConstraint(
            "length(trim(label)) BETWEEN 1 AND 300", name="ck_ro_checklist_label"
        ),
        sa.CheckConstraint(
            "(is_completed AND completed_at IS NOT NULL AND completed_by_user_id IS NOT NULL AND completed_by_name IS NOT NULL) OR (NOT is_completed AND completed_at IS NULL AND completed_by_user_id IS NULL AND completed_by_name IS NULL)",
            name="ck_ro_checklist_evidence",
        ),
    )
    op.create_index(
        "ix_repair_order_checklist_items_id", "repair_order_checklist_items", ["id"]
    )
    op.create_index(
        "ix_repair_order_checklist_items_labor_id",
        "repair_order_checklist_items",
        ["labor_id"],
    )
    op.create_index(
        "ix_ro_checklist_scope",
        "repair_order_checklist_items",
        ["tenant_id", "repair_order_id", "removed_at", "position", "id"],
    )


def downgrade():
    op.drop_table("repair_order_checklist_items")
    op.drop_column("services", "checklist_version")
    op.drop_column("services", "checklist_template")

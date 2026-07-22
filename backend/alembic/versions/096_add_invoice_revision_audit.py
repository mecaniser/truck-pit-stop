"""preserve voided invoice revisions

Revision ID: 096_invoice_revision_audit
Revises: 095_fleet_board_driver_phone
"""
from alembic import op
import sqlalchemy as sa


revision = "096_invoice_revision_audit"
down_revision = "095_fleet_board_driver_phone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("invoices", sa.Column("voided_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("invoices", sa.Column("voided_by_user_id", sa.UUID(), nullable=True))
    op.add_column("invoices", sa.Column("void_reason", sa.Text(), nullable=True))
    op.add_column("invoices", sa.Column("supersedes_invoice_id", sa.UUID(), nullable=True))
    op.create_foreign_key(
        "fk_invoices_voided_by_user_id_users",
        "invoices",
        "users",
        ["voided_by_user_id"],
        ["id"],
    )
    op.create_foreign_key(
        "fk_invoices_supersedes_invoice_id_invoices",
        "invoices",
        "invoices",
        ["supersedes_invoice_id"],
        ["id"],
    )

    # The original model declared repair_order_id unique. Invoice revisioning
    # retains cancelled rows, so replace that constraint with a normal lookup
    # index. Resolve the generated constraint name defensively.
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for constraint in inspector.get_unique_constraints("invoices"):
        if constraint.get("column_names") == ["repair_order_id"]:
            op.drop_constraint(constraint["name"], "invoices", type_="unique")
            break
    op.create_index("ix_invoices_repair_order_id", "invoices", ["repair_order_id"], unique=False)
    op.create_index(
        "ux_invoices_active_repair_order_id",
        "invoices",
        ["repair_order_id"],
        unique=True,
        postgresql_where=sa.text("status <> 'cancelled'"),
    )
    op.create_index(
        "ix_invoices_supersedes_invoice_id",
        "invoices",
        ["supersedes_invoice_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index("ix_invoices_supersedes_invoice_id", table_name="invoices")
    op.drop_index("ux_invoices_active_repair_order_id", table_name="invoices")
    op.drop_index("ix_invoices_repair_order_id", table_name="invoices")
    op.create_unique_constraint(
        "invoices_repair_order_id_key",
        "invoices",
        ["repair_order_id"],
    )
    op.drop_constraint(
        "fk_invoices_supersedes_invoice_id_invoices",
        "invoices",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_invoices_voided_by_user_id_users",
        "invoices",
        type_="foreignkey",
    )
    op.drop_column("invoices", "supersedes_invoice_id")
    op.drop_column("invoices", "void_reason")
    op.drop_column("invoices", "voided_by_user_id")
    op.drop_column("invoices", "voided_at")

"""version repair-order customer authorizations

Revision ID: 106_versioned_authorizations
Revises: 105_merge_invoice_qb_heads
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "106_versioned_authorizations"
down_revision = "105_merge_invoice_qb_heads"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    inspector = sa.inspect(bind)
    for constraint in inspector.get_unique_constraints("quotes"):
        if constraint.get("column_names") == ["repair_order_id"]:
            op.drop_constraint(constraint["name"], "quotes", type_="unique")
            break
    op.create_index("ix_quotes_repair_order_id", "quotes", ["repair_order_id"], unique=False)
    op.add_column("quotes", sa.Column("revision", sa.Integer(), nullable=True))
    op.add_column(
        "quotes",
        sa.Column("authorization_type", sa.String(length=32), nullable=True),
    )
    op.add_column(
        "quotes",
        sa.Column(
            "previously_authorized_amount",
            sa.Numeric(precision=10, scale=2),
            nullable=True,
        ),
    )
    op.add_column(
        "quotes",
        sa.Column("delta_amount", sa.Numeric(precision=10, scale=2), nullable=True),
    )
    op.add_column(
        "quotes",
        sa.Column("line_items_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        "quotes",
        sa.Column("decision_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.execute(
        """
        UPDATE quotes
        SET revision = 1,
            authorization_type = 'initial_estimate',
            previously_authorized_amount = 0,
            delta_amount = total_amount,
            decision_at = CASE WHEN is_approved OR is_declined THEN updated_at ELSE NULL END
        """
    )

    op.alter_column("quotes", "revision", nullable=False, server_default="1")
    op.alter_column(
        "quotes",
        "authorization_type",
        nullable=False,
        server_default="initial_estimate",
    )
    op.alter_column(
        "quotes",
        "previously_authorized_amount",
        nullable=False,
        server_default="0",
    )
    op.alter_column("quotes", "delta_amount", nullable=False, server_default="0")
    op.create_unique_constraint(
        "uq_quotes_repair_order_revision",
        "quotes",
        ["repair_order_id", "revision"],
    )


def downgrade() -> None:
    # Downgrade is only safe after removing all but revision 1 per repair order.
    op.drop_constraint("uq_quotes_repair_order_revision", "quotes", type_="unique")
    op.drop_column("quotes", "decision_at")
    op.drop_column("quotes", "line_items_snapshot")
    op.drop_column("quotes", "delta_amount")
    op.drop_column("quotes", "previously_authorized_amount")
    op.drop_column("quotes", "authorization_type")
    op.drop_column("quotes", "revision")
    op.drop_index("ix_quotes_repair_order_id", table_name="quotes")
    op.create_unique_constraint("quotes_repair_order_id_key", "quotes", ["repair_order_id"])

"""Reconcile provider-era DB-045 schemas with the bounded v1.1 contract.

Revision ID: 128_inventory_lifecycle_v11
Revises: 127_inventory_lifecycle

Revision 127 was exercised locally before Product reduced DB-045 from provider
payments to atomic manual tenders.  Some databases therefore have the original
provider-era 127 schema, while fresh environments may already contain the two
manual-reference columns from the reduced draft.  This additive compatibility
migration accepts either shape without relabelling the applied revision.

Provider-era tables and columns are intentionally retained.  The bounded v1.1
application does not use them, and deleting them here would turn a compatibility
repair into a destructive data migration.
"""
from alembic import op
import sqlalchemy as sa


revision = "128_inventory_lifecycle_v11"
down_revision = "127_inventory_lifecycle"
branch_labels = None
depends_on = None


def _column_names(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    if table_name not in inspector.get_table_names():
        return set()
    return {column["name"] for column in inspector.get_columns(table_name)}


def upgrade() -> None:
    bind = op.get_bind()

    attempt_columns = _column_names(bind, "counter_sale_payment_attempts")
    if "external_reference" not in attempt_columns:
        op.add_column(
            "counter_sale_payment_attempts",
            sa.Column("external_reference", sa.String(255), nullable=True),
        )
        attempt_columns.add("external_reference")
    if "provider_reference" in attempt_columns:
        op.execute(sa.text("""
            UPDATE counter_sale_payment_attempts
               SET external_reference = provider_reference
             WHERE external_reference IS NULL
               AND provider_reference IS NOT NULL
        """))
    op.alter_column(
        "counter_sale_payment_attempts",
        "state",
        existing_type=sa.String(40),
        existing_nullable=False,
        server_default="succeeded",
    )

    return_columns = _column_names(bind, "counter_sale_returns")
    if "refund_reference" not in return_columns:
        op.add_column(
            "counter_sale_returns",
            sa.Column("refund_reference", sa.String(255), nullable=True),
        )
        return_columns.add("refund_reference")

    table_names = set(sa.inspect(bind).get_table_names())
    if bind.dialect.name == "postgresql" and "counter_sale_refunds" in table_names:
        op.execute(sa.text("""
            UPDATE counter_sale_returns AS return_row
               SET refund_reference = prior_ref.reference
              FROM (
                    SELECT DISTINCT ON (tenant_id, return_id)
                           tenant_id,
                           return_id,
                           COALESCE(provider_reference, provider_refund_id) AS reference
                      FROM counter_sale_refunds
                     WHERE COALESCE(provider_reference, provider_refund_id) IS NOT NULL
                     ORDER BY tenant_id, return_id, created_at DESC, id DESC
                   ) AS prior_ref
             WHERE return_row.tenant_id = prior_ref.tenant_id
               AND return_row.id = prior_ref.return_id
               AND return_row.refund_reference IS NULL
        """))
    op.alter_column(
        "counter_sale_returns",
        "state",
        existing_type=sa.String(24),
        existing_nullable=False,
        server_default="completed",
    )
    if "fee_amount" in return_columns:
        op.alter_column(
            "counter_sale_returns",
            "fee_amount",
            existing_type=sa.Numeric(14, 2),
            existing_nullable=False,
            server_default=sa.text("0"),
        )

    return_line_columns = _column_names(bind, "counter_sale_return_lines")
    if "fee_amount" in return_line_columns:
        op.alter_column(
            "counter_sale_return_lines",
            "fee_amount",
            existing_type=sa.Numeric(14, 2),
            existing_nullable=False,
            server_default=sa.text("0"),
        )


def downgrade() -> None:
    bind = op.get_bind()
    table_names = set(sa.inspect(bind).get_table_names())
    if bind.dialect.name == "postgresql" and "counter_sales" in table_names:
        has_rows = bind.execute(sa.text("SELECT EXISTS (SELECT 1 FROM counter_sales)")).scalar()
        if has_rows:
            raise RuntimeError(
                "DB-045 v1.1 compatibility downgrade refused: counter-sale rows exist"
            )

    return_line_columns = _column_names(bind, "counter_sale_return_lines")
    if "fee_amount" in return_line_columns:
        op.alter_column(
            "counter_sale_return_lines",
            "fee_amount",
            existing_type=sa.Numeric(14, 2),
            existing_nullable=False,
            server_default=None,
        )

    return_columns = _column_names(bind, "counter_sale_returns")
    if "fee_amount" in return_columns:
        op.alter_column(
            "counter_sale_returns",
            "fee_amount",
            existing_type=sa.Numeric(14, 2),
            existing_nullable=False,
            server_default=None,
        )
    if "state" in return_columns:
        op.alter_column(
            "counter_sale_returns",
            "state",
            existing_type=sa.String(24),
            existing_nullable=False,
            server_default=None,
        )

    attempt_columns = _column_names(bind, "counter_sale_payment_attempts")
    if "state" in attempt_columns:
        op.alter_column(
            "counter_sale_payment_attempts",
            "state",
            existing_type=sa.String(40),
            existing_nullable=False,
            server_default=None,
        )

    # external_reference and refund_reference are intentionally retained.  A
    # downgrade must not erase copied or newly recorded audit references, and
    # revision 127 code safely ignores these nullable additive columns.

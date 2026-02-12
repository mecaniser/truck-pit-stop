"""Add payment number counters

Revision ID: 027
Revises: 026
Create Date: 2026-02-11
"""
import uuid
from datetime import datetime, timezone

from alembic import op
import sqlalchemy as sa


# revision identifiers
revision = "027"
down_revision = "026"
branch_labels = None
depends_on = None


def _get_existing_indexes(bind, table_name: str) -> set[str]:
    inspector = sa.inspect(bind)
    return {index["name"] for index in inspector.get_indexes(table_name)}


def upgrade() -> None:
    bind = op.get_bind()

    op.create_table(
        "payment_number_counters",
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("last_number", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_payment_number_counters_id", "payment_number_counters", ["id"], unique=False)
    op.create_index("ix_payment_number_counters_tenant_id", "payment_number_counters", ["tenant_id"], unique=True)

    # Keep the existing safety net for uniqueness on payment_number if a drifted
    # environment somehow lacks it.
    payments_indexes = _get_existing_indexes(bind, "payments")
    if "ix_payments_payment_number" not in payments_indexes:
        op.create_index("ix_payments_payment_number", "payments", ["payment_number"], unique=True)

    if "ix_payments_tenant_id_payment_number" not in payments_indexes:
        op.create_index(
            "ix_payments_tenant_id_payment_number",
            "payments",
            ["tenant_id", "payment_number"],
            unique=False,
        )

    tenant_rows = bind.execute(sa.text("SELECT id FROM tenants")).fetchall()
    payment_rows = bind.execute(sa.text("SELECT tenant_id, payment_number FROM payments")).fetchall()

    max_by_tenant = {row[0]: 0 for row in tenant_rows}
    for tenant_id, payment_number in payment_rows:
        if not payment_number:
            continue
        parts = str(payment_number).split("-")
        if not parts:
            continue
        suffix = parts[-1]
        if not suffix.isdigit():
            continue
        numeric_suffix = int(suffix)
        current = max_by_tenant.get(tenant_id, 0)
        if numeric_suffix > current:
            max_by_tenant[tenant_id] = numeric_suffix

    now = datetime.now(timezone.utc)
    insert_rows = [
        {
            "id": uuid.uuid4(),
            "tenant_id": tenant_id,
            "last_number": max_by_tenant.get(tenant_id, 0),
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        for tenant_id in max_by_tenant.keys()
    ]
    if insert_rows:
        counters_table = sa.table(
            "payment_number_counters",
            sa.column("id", sa.UUID()),
            sa.column("tenant_id", sa.UUID()),
            sa.column("last_number", sa.Integer()),
            sa.column("created_at", sa.DateTime(timezone=True)),
            sa.column("updated_at", sa.DateTime(timezone=True)),
            sa.column("deleted_at", sa.DateTime(timezone=True)),
        )
        op.bulk_insert(counters_table, insert_rows)


def downgrade() -> None:
    bind = op.get_bind()
    payments_indexes = _get_existing_indexes(bind, "payments")
    if "ix_payments_tenant_id_payment_number" in payments_indexes:
        op.drop_index("ix_payments_tenant_id_payment_number", table_name="payments")

    op.drop_index("ix_payment_number_counters_tenant_id", table_name="payment_number_counters")
    op.drop_index("ix_payment_number_counters_id", table_name="payment_number_counters")
    op.drop_table("payment_number_counters")

"""add contacts table and source-tracking columns for external imports

Customer.source already existed (e.g. "zelle", "walk_in") but vehicles,
repair_orders, inventory, invoices, and payments had no way to record where
a row came from. Adding a nullable source column to each so imported data
(starting with the Easy Truck Shop migration) can be identified and queried
separately from organically-created records, without guessing based on
which customer a row belongs to.

Also adds a Contact model: a customer (company) can have multiple named
people associated with it (owner, dispatcher, driver, etc.) — the Customer
row's own first_name/last_name/email/phone is not enough to represent that,
so this is a proper one-to-many table rather than continuing to squash
multiple real contacts into one Customer row.

Revision ID: 068
Revises: 067
Create Date: 2026-07-08
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid


revision = "068"
down_revision = "067"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "contacts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, index=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False, index=True),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("customers.id"), nullable=False, index=True),
        sa.Column("first_name", sa.String(100), nullable=True),
        sa.Column("last_name", sa.String(100), nullable=True),
        sa.Column("role", sa.String(100), nullable=True),
        sa.Column("email", sa.String(255), nullable=True, index=True),
        sa.Column("phone", sa.String(20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("is_primary", sa.Boolean(), nullable=False, server_default=sa.false(), index=True),
        sa.Column("source", sa.String(50), nullable=True, index=True),
    )

    for table in ("vehicles", "repair_orders", "inventory", "invoices", "payments"):
        op.add_column(table, sa.Column("source", sa.String(50), nullable=True))
        op.create_index(f"ix_{table}_source", table, ["source"])


def downgrade() -> None:
    for table in ("vehicles", "repair_orders", "inventory", "invoices", "payments"):
        op.drop_index(f"ix_{table}_source", table_name=table)
        op.drop_column(table, "source")

    op.drop_table("contacts")

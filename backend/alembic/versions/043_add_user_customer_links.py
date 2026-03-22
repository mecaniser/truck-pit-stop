"""add user_customer_links for cross-tenant customer identity

Revision ID: 043
Revises: 042
Create Date: 2026-03-21
"""
from alembic import op
import sqlalchemy as sa


revision = "043"
down_revision = "042"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "user_customer_links",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("user_id", sa.UUID(), nullable=False),
        sa.Column("customer_id", sa.UUID(), nullable=False),
        sa.Column("tenant_id", sa.UUID(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "tenant_id", name="uq_user_customer_link_user_tenant"),
    )
    op.create_index("ix_user_customer_links_id", "user_customer_links", ["id"])
    op.create_index("ix_user_customer_links_user_id", "user_customer_links", ["user_id"])
    op.create_index("ix_user_customer_links_tenant_id", "user_customer_links", ["tenant_id"])
    op.create_index("ix_user_customer_links_customer_id", "user_customer_links", ["customer_id"])

    # Backfill existing customer users into the join table
    op.execute("""
        INSERT INTO user_customer_links (id, user_id, customer_id, tenant_id, created_at, updated_at)
        SELECT gen_random_uuid(), u.id, u.customer_id, u.tenant_id, NOW(), NOW()
        FROM users u
        WHERE u.role = 'customer'
          AND u.customer_id IS NOT NULL
          AND u.tenant_id IS NOT NULL
          AND u.deleted_at IS NULL
        ON CONFLICT ON CONSTRAINT uq_user_customer_link_user_tenant DO NOTHING
    """)


def downgrade() -> None:
    op.drop_index("ix_user_customer_links_customer_id", "user_customer_links")
    op.drop_index("ix_user_customer_links_tenant_id", "user_customer_links")
    op.drop_index("ix_user_customer_links_user_id", "user_customer_links")
    op.drop_index("ix_user_customer_links_id", "user_customer_links")
    op.drop_table("user_customer_links")

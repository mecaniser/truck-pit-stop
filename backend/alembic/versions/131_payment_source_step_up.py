"""Add server-enforced payment-source step-up grants.

Revision ID: 131_payment_source_step_up
Revises: 130_repair_order_shop_notes
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "131_payment_source_step_up"
down_revision = "130_repair_order_shop_notes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "payment_step_up_grants",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_jti", sa.String(length=64), nullable=False),
        sa.Column("token_version", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("scope", sa.String(length=96), nullable=False),
        sa.Column("token_digest", sa.String(length=64), nullable=False),
        sa.Column("one_time", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["target_tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("token_digest", name="uq_payment_step_up_grant_digest"),
    )
    for column in (
        "id", "tenant_id", "target_tenant_id", "user_id", "session_jti",
        "scope", "token_digest", "expires_at", "consumed_at", "revoked_at",
    ):
        op.create_index(f"ix_payment_step_up_grants_{column}", "payment_step_up_grants", [column])

    op.create_table(
        "payment_step_up_audit_events",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("target_tenant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("grant_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("event_type", sa.String(length=24), nullable=False),
        sa.Column("scope", sa.String(length=96), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=True),
        sa.Column("correlation_id", sa.String(length=64), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["target_tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["grant_id"], ["payment_step_up_grants.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in (
        "id", "tenant_id", "target_tenant_id", "user_id", "grant_id",
        "event_type", "scope", "provider", "correlation_id",
    ):
        op.create_index(f"ix_payment_step_up_audit_events_{column}", "payment_step_up_audit_events", [column])
    op.execute("""
        CREATE FUNCTION reject_payment_step_up_audit_mutation() RETURNS trigger AS $$
        BEGIN
          RAISE EXCEPTION 'payment_step_up_audit_events is append-only';
        END;
        $$ LANGUAGE plpgsql
    """)
    op.execute("""
        CREATE TRIGGER trg_payment_step_up_audit_no_update_delete
        BEFORE UPDATE OR DELETE ON payment_step_up_audit_events
        FOR EACH ROW EXECUTE FUNCTION reject_payment_step_up_audit_mutation()
    """)

    op.add_column("quickbooks_oauth_states", sa.Column("step_up_grant_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("quickbooks_oauth_states", sa.Column("step_up_scope", sa.String(length=96), nullable=True))
    op.add_column("quickbooks_oauth_states", sa.Column("step_up_verified_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key(
        "fk_qb_oauth_state_step_up_grant",
        "quickbooks_oauth_states",
        "payment_step_up_grants",
        ["step_up_grant_id"],
        ["id"],
    )
    op.create_index("ix_quickbooks_oauth_states_step_up_grant_id", "quickbooks_oauth_states", ["step_up_grant_id"])


def downgrade() -> None:
    op.drop_index("ix_quickbooks_oauth_states_step_up_grant_id", table_name="quickbooks_oauth_states")
    op.drop_constraint("fk_qb_oauth_state_step_up_grant", "quickbooks_oauth_states", type_="foreignkey")
    op.drop_column("quickbooks_oauth_states", "step_up_verified_at")
    op.drop_column("quickbooks_oauth_states", "step_up_scope")
    op.drop_column("quickbooks_oauth_states", "step_up_grant_id")

    op.execute("DROP TRIGGER IF EXISTS trg_payment_step_up_audit_no_update_delete ON payment_step_up_audit_events")
    op.execute("DROP FUNCTION IF EXISTS reject_payment_step_up_audit_mutation()")

    for column in (
        "correlation_id", "provider", "scope", "event_type", "grant_id",
        "user_id", "target_tenant_id", "tenant_id", "id",
    ):
        op.drop_index(f"ix_payment_step_up_audit_events_{column}", table_name="payment_step_up_audit_events")
    op.drop_table("payment_step_up_audit_events")

    for column in (
        "revoked_at", "consumed_at", "expires_at", "token_digest", "scope",
        "session_jti", "user_id", "target_tenant_id", "tenant_id", "id",
    ):
        op.drop_index(f"ix_payment_step_up_grants_{column}", table_name="payment_step_up_grants")
    op.drop_table("payment_step_up_grants")

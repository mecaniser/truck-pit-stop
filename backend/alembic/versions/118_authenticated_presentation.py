"""Add authenticated staff presentation preferences and rollout state.

Revision ID: 118_authenticated_presentation
Revises: 117_conversion_export_security
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "118_authenticated_presentation"
down_revision = "117_conversion_export_security"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "tenants",
        sa.Column(
            "staff_presentation_default",
            sa.String(length=16),
            nullable=False,
            server_default="legacy",
        ),
    )
    op.create_table(
        "user_appearance_preferences",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("schema_version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("appearance", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
        sa.Column("legacy_migration_status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("legacy_migrated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_user_appearance_preferences_tenant_id", "user_appearance_preferences", ["tenant_id"])
    op.create_index("ix_user_appearance_preferences_user_id", "user_appearance_preferences", ["user_id"])
    op.create_index(
        "uq_user_appearance_preferences_active_tenant_user",
        "user_appearance_preferences",
        ["tenant_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )
    op.create_table(
        "user_presentation_overrides",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("user_id", sa.Uuid(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("presentation", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_user_presentation_overrides_tenant_id", "user_presentation_overrides", ["tenant_id"])
    op.create_index("ix_user_presentation_overrides_user_id", "user_presentation_overrides", ["user_id"])
    op.create_index(
        "uq_user_presentation_overrides_active_tenant_user",
        "user_presentation_overrides",
        ["tenant_id", "user_id"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_table("user_presentation_overrides")
    op.drop_table("user_appearance_preferences")
    op.drop_column("tenants", "staff_presentation_default")

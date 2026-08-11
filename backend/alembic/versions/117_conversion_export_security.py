"""Add conversion-export security audit storage.

Revision ID: 117_conversion_export_security
Revises: 116_invitation_identity_review
"""
from alembic import op
import sqlalchemy as sa


revision = "117_conversion_export_security"
down_revision = "116_invitation_identity_review"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "conversion_export_audits",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("tenant_id", sa.Uuid(), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("actor_user_id", sa.Uuid(), sa.ForeignKey("users.id")),
        sa.Column("actor_api_key_id", sa.Uuid(), sa.ForeignKey("conversion_api_keys.id")),
        sa.Column("action", sa.String(80), nullable=False),
        sa.Column("target_type", sa.String(40), nullable=False),
        sa.Column("target_id", sa.Uuid()),
        sa.Column("metadata_json", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    for name in ("tenant_id", "actor_user_id", "actor_api_key_id", "action", "target_id"):
        op.create_index(f"ix_conversion_export_audits_{name}", "conversion_export_audits", [name])


def downgrade() -> None:
    op.drop_table("conversion_export_audits")

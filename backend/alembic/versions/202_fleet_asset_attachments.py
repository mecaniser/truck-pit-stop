"""Dated tractor/trailer attachments; permanent service histories stay on vehicles."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision = "202_fleet_asset_attachments"
down_revision = "201_customer_payment_profiles"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "fleet_asset_attachments",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.Column("tenant_id", UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("tractor_id", UUID(as_uuid=True), nullable=False),
        sa.Column("trailer_id", UUID(as_uuid=True), nullable=False),
        sa.Column("attached_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("detached_at", sa.DateTime(timezone=True)),
        sa.Column("attached_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("detached_by_user_id", UUID(as_uuid=True), sa.ForeignKey("users.id")),
        sa.ForeignKeyConstraint(["tenant_id", "tractor_id"], ["vehicles.tenant_id", "vehicles.id"], name="fk_fleet_attachment_tractor"),
        sa.ForeignKeyConstraint(["tenant_id", "trailer_id"], ["vehicles.tenant_id", "vehicles.id"], name="fk_fleet_attachment_trailer"),
        sa.CheckConstraint("tractor_id != trailer_id", name="ck_fleet_attachment_distinct_assets"),
        sa.CheckConstraint("detached_at IS NULL OR detached_at >= attached_at", name="ck_fleet_attachment_dates"),
    )
    for column in ("id", "tenant_id", "tractor_id", "trailer_id"):
        op.create_index(f"ix_fleet_asset_attachments_{column}", "fleet_asset_attachments", [column])
    for role in ("tractor", "trailer"):
        op.create_index(
            f"uq_fleet_attachment_active_{role}", "fleet_asset_attachments", [f"{role}_id"], unique=True,
            postgresql_where=sa.text("detached_at IS NULL AND deleted_at IS NULL"),
        )


def downgrade():
    op.drop_table("fleet_asset_attachments")

"""Customer-scoped optional notification choices; existing delivery stays enabled."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "204_customer_notif_preferences"
down_revision = "203_customer_efs_submissions"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "customer_notification_preferences",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False),
        *[sa.Column(name, sa.Boolean(), nullable=False, server_default=sa.true())
          for name in ("invoice_email", "invoice_sms", "repair_email", "repair_sms")],
        sa.Column("updated_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint("tenant_id", "customer_id", name="uq_customer_notification_preferences_scope"),
        sa.ForeignKeyConstraint(["tenant_id", "customer_id"], ["customers.tenant_id", "customers.id"], ondelete="CASCADE"),
        sa.CheckConstraint("revision >= 1", name="ck_customer_notification_preferences_revision"),
    )
    op.create_index("ix_customer_notification_preferences_tenant_id", "customer_notification_preferences", ["tenant_id"])
    op.create_index("ix_customer_notification_preferences_customer_id", "customer_notification_preferences", ["customer_id"])


def downgrade():
    op.drop_table("customer_notification_preferences")

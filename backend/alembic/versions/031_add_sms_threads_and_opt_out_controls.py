"""Add SMS threads, message storage, and opt-out controls

Revision ID: 031
Revises: 030
Create Date: 2026-02-12
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "031"
down_revision = "030"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "customers",
        sa.Column("sms_opt_out", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("customers", sa.Column("sms_opted_out_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("customers", sa.Column("sms_opt_out_source", sa.String(length=50), nullable=True))
    op.create_index("ix_customers_sms_opt_out", "customers", ["sms_opt_out"], unique=False)
    op.alter_column("customers", "sms_opt_out", server_default=None)

    op.add_column("tenants", sa.Column("sms_phone_number", sa.String(length=20), nullable=True))
    op.add_column("tenants", sa.Column("sms_phone_sid", sa.String(length=64), nullable=True))
    op.add_column(
        "tenants",
        sa.Column("sms_enabled", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    op.add_column("tenants", sa.Column("sms_messaging_service_sid", sa.String(length=64), nullable=True))
    op.create_index("ix_tenants_sms_phone_number", "tenants", ["sms_phone_number"], unique=True)
    op.alter_column("tenants", "sms_enabled", server_default=None)

    message_direction_enum = postgresql.ENUM(
        "inbound",
        "outbound",
        name="sms_message_direction",
        create_type=False,
    )
    message_source_enum = postgresql.ENUM(
        "inbound",
        "manual",
        "automated",
        name="sms_message_source",
        create_type=False,
    )
    delivery_status_enum = postgresql.ENUM(
        "pending",
        "queued",
        "sent",
        "delivered",
        "undelivered",
        "failed",
        name="sms_delivery_status",
        create_type=False,
    )
    message_direction_enum.create(op.get_bind(), checkfirst=True)
    message_source_enum.create(op.get_bind(), checkfirst=True)
    delivery_status_enum.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "message_threads",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_phone", sa.String(length=20), nullable=True),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_message_preview", sa.Text(), nullable=True),
        sa.Column("unread_count_staff", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("tenant_id", "customer_id", name="uq_message_threads_tenant_customer"),
    )
    op.create_index("ix_message_threads_tenant_id", "message_threads", ["tenant_id"], unique=False)
    op.create_index("ix_message_threads_customer_id", "message_threads", ["customer_id"], unique=False)
    op.create_index("ix_message_threads_last_message_at", "message_threads", ["last_message_at"], unique=False)
    op.create_index(
        "ix_message_threads_tenant_last_message",
        "message_threads",
        ["tenant_id", "last_message_at"],
        unique=False,
    )

    op.create_table(
        "sms_messages",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("thread_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("customer_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("direction", message_direction_enum, nullable=False),
        sa.Column("source", message_source_enum, nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("from_number", sa.String(length=20), nullable=True),
        sa.Column("to_number", sa.String(length=20), nullable=True),
        sa.Column("twilio_message_sid", sa.String(length=64), nullable=True),
        sa.Column("delivery_status", delivery_status_enum, nullable=False, server_default="pending"),
        sa.Column("error_code", sa.String(length=32), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("delivered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["thread_id"], ["message_threads.id"]),
        sa.ForeignKeyConstraint(["customer_id"], ["customers.id"]),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_sms_messages_tenant_id", "sms_messages", ["tenant_id"], unique=False)
    op.create_index("ix_sms_messages_thread_id", "sms_messages", ["thread_id"], unique=False)
    op.create_index("ix_sms_messages_customer_id", "sms_messages", ["customer_id"], unique=False)
    op.create_index("ix_sms_messages_created_by_user_id", "sms_messages", ["created_by_user_id"], unique=False)
    op.create_index("ix_sms_messages_direction", "sms_messages", ["direction"], unique=False)
    op.create_index("ix_sms_messages_source", "sms_messages", ["source"], unique=False)
    op.create_index("ix_sms_messages_delivery_status", "sms_messages", ["delivery_status"], unique=False)
    op.create_index("ix_sms_messages_twilio_message_sid", "sms_messages", ["twilio_message_sid"], unique=True)
    op.create_index("ix_sms_messages_thread_created_at", "sms_messages", ["thread_id", "created_at"], unique=False)
    op.alter_column("sms_messages", "delivery_status", server_default=None)


def downgrade() -> None:
    op.drop_index("ix_sms_messages_thread_created_at", table_name="sms_messages")
    op.drop_index("ix_sms_messages_twilio_message_sid", table_name="sms_messages")
    op.drop_index("ix_sms_messages_delivery_status", table_name="sms_messages")
    op.drop_index("ix_sms_messages_source", table_name="sms_messages")
    op.drop_index("ix_sms_messages_direction", table_name="sms_messages")
    op.drop_index("ix_sms_messages_created_by_user_id", table_name="sms_messages")
    op.drop_index("ix_sms_messages_customer_id", table_name="sms_messages")
    op.drop_index("ix_sms_messages_thread_id", table_name="sms_messages")
    op.drop_index("ix_sms_messages_tenant_id", table_name="sms_messages")
    op.drop_table("sms_messages")

    op.drop_index("ix_message_threads_tenant_last_message", table_name="message_threads")
    op.drop_index("ix_message_threads_last_message_at", table_name="message_threads")
    op.drop_index("ix_message_threads_customer_id", table_name="message_threads")
    op.drop_index("ix_message_threads_tenant_id", table_name="message_threads")
    op.drop_table("message_threads")

    op.execute("DROP TYPE IF EXISTS sms_delivery_status")
    op.execute("DROP TYPE IF EXISTS sms_message_source")
    op.execute("DROP TYPE IF EXISTS sms_message_direction")

    op.drop_index("ix_tenants_sms_phone_number", table_name="tenants")
    op.drop_column("tenants", "sms_messaging_service_sid")
    op.drop_column("tenants", "sms_enabled")
    op.drop_column("tenants", "sms_phone_sid")
    op.drop_column("tenants", "sms_phone_number")

    op.drop_index("ix_customers_sms_opt_out", table_name="customers")
    op.drop_column("customers", "sms_opt_out_source")
    op.drop_column("customers", "sms_opted_out_at")
    op.drop_column("customers", "sms_opt_out")

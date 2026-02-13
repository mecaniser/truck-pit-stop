"""Add mechanic utilization tracking tables and workforce settings

Revision ID: 032
Revises: 031
Create Date: 2026-02-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "032"
down_revision = "031"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Tenant workforce settings
    op.add_column(
        "tenants",
        sa.Column("timezone", sa.String(length=64), nullable=False, server_default="America/New_York"),
    )
    op.add_column(
        "tenants",
        sa.Column("default_core_hours_minutes", sa.Integer(), nullable=False, server_default="480"),
    )
    op.add_column(
        "tenants",
        sa.Column("default_shift_start_local", sa.String(length=5), nullable=False, server_default="08:00"),
    )
    op.add_column(
        "tenants",
        sa.Column("default_shift_end_local", sa.String(length=5), nullable=False, server_default="18:00"),
    )
    op.alter_column("tenants", "timezone", server_default=None)
    op.alter_column("tenants", "default_core_hours_minutes", server_default=None)
    op.alter_column("tenants", "default_shift_start_local", server_default=None)
    op.alter_column("tenants", "default_shift_end_local", server_default=None)

    # Per-mechanic optional overrides
    op.add_column("users", sa.Column("core_hours_target_minutes_override", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("shift_start_local_override", sa.String(length=5), nullable=True))
    op.add_column("users", sa.Column("shift_end_local_override", sa.String(length=5), nullable=True))

    # Enums for session storage
    mechanic_session_type = postgresql.ENUM(
        "repair_order",
        "misc",
        name="mechanic_session_type",
        create_type=False,
    )
    misc_work_category = postgresql.ENUM(
        "shop_cleanup",
        "parts_runner",
        "admin_paperwork",
        "training",
        "shop_support",
        "other",
        name="misc_work_category",
        create_type=False,
    )
    mechanic_session_type.create(op.get_bind(), checkfirst=True)
    misc_work_category.create(op.get_bind(), checkfirst=True)

    op.create_table(
        "mechanic_time_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mechanic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("repair_order_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_type", mechanic_session_type, nullable=False),
        sa.Column("misc_category", misc_work_category, nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("stopped_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("stop_reason", sa.String(length=50), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["mechanic_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["repair_order_id"], ["repair_orders.id"]),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["stopped_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mechanic_time_sessions_tenant_id", "mechanic_time_sessions", ["tenant_id"], unique=False)
    op.create_index("ix_mechanic_time_sessions_mechanic_id", "mechanic_time_sessions", ["mechanic_id"], unique=False)
    op.create_index("ix_mechanic_time_sessions_repair_order_id", "mechanic_time_sessions", ["repair_order_id"], unique=False)
    op.create_index("ix_mechanic_time_sessions_session_type", "mechanic_time_sessions", ["session_type"], unique=False)
    op.create_index("ix_mechanic_time_sessions_misc_category", "mechanic_time_sessions", ["misc_category"], unique=False)
    op.create_index("ix_mechanic_time_sessions_started_at", "mechanic_time_sessions", ["started_at"], unique=False)
    op.create_index("ix_mechanic_time_sessions_ended_at", "mechanic_time_sessions", ["ended_at"], unique=False)
    op.create_index("ix_mechanic_time_sessions_started_by_user_id", "mechanic_time_sessions", ["started_by_user_id"], unique=False)
    op.create_index("ix_mechanic_time_sessions_stopped_by_user_id", "mechanic_time_sessions", ["stopped_by_user_id"], unique=False)
    op.create_index(
        "uq_mechanic_time_sessions_active_mechanic",
        "mechanic_time_sessions",
        ["mechanic_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL AND deleted_at IS NULL"),
    )

    op.create_table(
        "mechanic_time_session_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mechanic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_role", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("manager_reason", sa.Text(), nullable=True),
        sa.Column("before_snapshot", sa.JSON(), nullable=True),
        sa.Column("after_snapshot", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["session_id"], ["mechanic_time_sessions.id"]),
        sa.ForeignKeyConstraint(["mechanic_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mechanic_time_session_audit_tenant_id", "mechanic_time_session_audit", ["tenant_id"], unique=False)
    op.create_index("ix_mechanic_time_session_audit_session_id", "mechanic_time_session_audit", ["session_id"], unique=False)
    op.create_index("ix_mechanic_time_session_audit_mechanic_id", "mechanic_time_session_audit", ["mechanic_id"], unique=False)
    op.create_index("ix_mechanic_time_session_audit_actor_user_id", "mechanic_time_session_audit", ["actor_user_id"], unique=False)
    op.create_index("ix_mechanic_time_session_audit_action", "mechanic_time_session_audit", ["action"], unique=False)

    op.create_table(
        "mechanic_idle_alert_streaks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mechanic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("alert_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["mechanic_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mechanic_idle_alert_streaks_tenant_id", "mechanic_idle_alert_streaks", ["tenant_id"], unique=False)
    op.create_index("ix_mechanic_idle_alert_streaks_mechanic_id", "mechanic_idle_alert_streaks", ["mechanic_id"], unique=False)
    op.create_index("ix_mechanic_idle_alert_streaks_local_date", "mechanic_idle_alert_streaks", ["local_date"], unique=False)
    op.create_index("ix_mechanic_idle_alert_streaks_is_active", "mechanic_idle_alert_streaks", ["is_active"], unique=False)
    op.create_index(
        "uq_mechanic_idle_alert_streaks_active_daily",
        "mechanic_idle_alert_streaks",
        ["tenant_id", "mechanic_id", "local_date"],
        unique=True,
        postgresql_where=sa.text("is_active = true AND deleted_at IS NULL"),
    )
    op.alter_column("mechanic_idle_alert_streaks", "is_active", server_default=None)


def downgrade() -> None:
    op.drop_index("uq_mechanic_idle_alert_streaks_active_daily", table_name="mechanic_idle_alert_streaks")
    op.drop_index("ix_mechanic_idle_alert_streaks_is_active", table_name="mechanic_idle_alert_streaks")
    op.drop_index("ix_mechanic_idle_alert_streaks_local_date", table_name="mechanic_idle_alert_streaks")
    op.drop_index("ix_mechanic_idle_alert_streaks_mechanic_id", table_name="mechanic_idle_alert_streaks")
    op.drop_index("ix_mechanic_idle_alert_streaks_tenant_id", table_name="mechanic_idle_alert_streaks")
    op.drop_table("mechanic_idle_alert_streaks")

    op.drop_index("ix_mechanic_time_session_audit_action", table_name="mechanic_time_session_audit")
    op.drop_index("ix_mechanic_time_session_audit_actor_user_id", table_name="mechanic_time_session_audit")
    op.drop_index("ix_mechanic_time_session_audit_mechanic_id", table_name="mechanic_time_session_audit")
    op.drop_index("ix_mechanic_time_session_audit_session_id", table_name="mechanic_time_session_audit")
    op.drop_index("ix_mechanic_time_session_audit_tenant_id", table_name="mechanic_time_session_audit")
    op.drop_table("mechanic_time_session_audit")

    op.drop_index("uq_mechanic_time_sessions_active_mechanic", table_name="mechanic_time_sessions")
    op.drop_index("ix_mechanic_time_sessions_stopped_by_user_id", table_name="mechanic_time_sessions")
    op.drop_index("ix_mechanic_time_sessions_started_by_user_id", table_name="mechanic_time_sessions")
    op.drop_index("ix_mechanic_time_sessions_ended_at", table_name="mechanic_time_sessions")
    op.drop_index("ix_mechanic_time_sessions_started_at", table_name="mechanic_time_sessions")
    op.drop_index("ix_mechanic_time_sessions_misc_category", table_name="mechanic_time_sessions")
    op.drop_index("ix_mechanic_time_sessions_session_type", table_name="mechanic_time_sessions")
    op.drop_index("ix_mechanic_time_sessions_repair_order_id", table_name="mechanic_time_sessions")
    op.drop_index("ix_mechanic_time_sessions_mechanic_id", table_name="mechanic_time_sessions")
    op.drop_index("ix_mechanic_time_sessions_tenant_id", table_name="mechanic_time_sessions")
    op.drop_table("mechanic_time_sessions")

    op.execute("DROP TYPE IF EXISTS misc_work_category")
    op.execute("DROP TYPE IF EXISTS mechanic_session_type")

    op.drop_column("users", "shift_end_local_override")
    op.drop_column("users", "shift_start_local_override")
    op.drop_column("users", "core_hours_target_minutes_override")

    op.drop_column("tenants", "default_shift_end_local")
    op.drop_column("tenants", "default_shift_start_local")
    op.drop_column("tenants", "default_core_hours_minutes")
    op.drop_column("tenants", "timezone")

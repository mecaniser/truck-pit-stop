"""Add mechanic attendance and break tracking

Revision ID: 033
Revises: 032
Create Date: 2026-02-13
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "033"
down_revision = "032"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "mechanic_attendance_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mechanic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("local_date", sa.Date(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ended_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("start_source", sa.String(length=50), nullable=False, server_default="manual_clock_in"),
        sa.Column("end_source", sa.String(length=50), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("snapshot_timezone", sa.String(length=64), nullable=False),
        sa.Column("snapshot_core_target_minutes", sa.Integer(), nullable=False),
        sa.Column("snapshot_shift_start_local", sa.String(length=5), nullable=False),
        sa.Column("snapshot_shift_end_local", sa.String(length=5), nullable=False),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["mechanic_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["ended_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.alter_column("mechanic_attendance_sessions", "start_source", server_default=None)
    op.create_index("ix_mechanic_attendance_sessions_tenant_id", "mechanic_attendance_sessions", ["tenant_id"], unique=False)
    op.create_index("ix_mechanic_attendance_sessions_mechanic_id", "mechanic_attendance_sessions", ["mechanic_id"], unique=False)
    op.create_index("ix_mechanic_attendance_sessions_local_date", "mechanic_attendance_sessions", ["local_date"], unique=False)
    op.create_index("ix_mechanic_attendance_sessions_started_at", "mechanic_attendance_sessions", ["started_at"], unique=False)
    op.create_index("ix_mechanic_attendance_sessions_ended_at", "mechanic_attendance_sessions", ["ended_at"], unique=False)
    op.create_index("ix_mechanic_attendance_sessions_started_by_user_id", "mechanic_attendance_sessions", ["started_by_user_id"], unique=False)
    op.create_index("ix_mechanic_attendance_sessions_ended_by_user_id", "mechanic_attendance_sessions", ["ended_by_user_id"], unique=False)
    op.create_index(
        "uq_mechanic_attendance_sessions_active_mechanic",
        "mechanic_attendance_sessions",
        ["mechanic_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL AND deleted_at IS NULL"),
    )

    op.create_table(
        "mechanic_break_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("mechanic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attendance_session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_by_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("ended_by_user_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("start_source", sa.String(length=50), nullable=False, server_default="manual_break_start"),
        sa.Column("end_source", sa.String(length=50), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["mechanic_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["attendance_session_id"], ["mechanic_attendance_sessions.id"]),
        sa.ForeignKeyConstraint(["started_by_user_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["ended_by_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.alter_column("mechanic_break_sessions", "start_source", server_default=None)
    op.create_index("ix_mechanic_break_sessions_tenant_id", "mechanic_break_sessions", ["tenant_id"], unique=False)
    op.create_index("ix_mechanic_break_sessions_mechanic_id", "mechanic_break_sessions", ["mechanic_id"], unique=False)
    op.create_index("ix_mechanic_break_sessions_attendance_session_id", "mechanic_break_sessions", ["attendance_session_id"], unique=False)
    op.create_index("ix_mechanic_break_sessions_started_at", "mechanic_break_sessions", ["started_at"], unique=False)
    op.create_index("ix_mechanic_break_sessions_ended_at", "mechanic_break_sessions", ["ended_at"], unique=False)
    op.create_index("ix_mechanic_break_sessions_started_by_user_id", "mechanic_break_sessions", ["started_by_user_id"], unique=False)
    op.create_index("ix_mechanic_break_sessions_ended_by_user_id", "mechanic_break_sessions", ["ended_by_user_id"], unique=False)
    op.create_index(
        "uq_mechanic_break_sessions_active_mechanic",
        "mechanic_break_sessions",
        ["mechanic_id"],
        unique=True,
        postgresql_where=sa.text("ended_at IS NULL AND deleted_at IS NULL"),
    )

    op.create_table(
        "mechanic_attendance_audit",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("attendance_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("break_session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("mechanic_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_user_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("actor_role", sa.String(length=32), nullable=False),
        sa.Column("action", sa.String(length=50), nullable=False),
        sa.Column("manager_reason", sa.Text(), nullable=True),
        sa.Column("before_snapshot", sa.JSON(), nullable=True),
        sa.Column("after_snapshot", sa.JSON(), nullable=True),
        sa.ForeignKeyConstraint(["tenant_id"], ["tenants.id"]),
        sa.ForeignKeyConstraint(["attendance_session_id"], ["mechanic_attendance_sessions.id"]),
        sa.ForeignKeyConstraint(["break_session_id"], ["mechanic_break_sessions.id"]),
        sa.ForeignKeyConstraint(["mechanic_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["actor_user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_mechanic_attendance_audit_tenant_id", "mechanic_attendance_audit", ["tenant_id"], unique=False)
    op.create_index("ix_mechanic_attendance_audit_attendance_session_id", "mechanic_attendance_audit", ["attendance_session_id"], unique=False)
    op.create_index("ix_mechanic_attendance_audit_break_session_id", "mechanic_attendance_audit", ["break_session_id"], unique=False)
    op.create_index("ix_mechanic_attendance_audit_mechanic_id", "mechanic_attendance_audit", ["mechanic_id"], unique=False)
    op.create_index("ix_mechanic_attendance_audit_actor_user_id", "mechanic_attendance_audit", ["actor_user_id"], unique=False)
    op.create_index("ix_mechanic_attendance_audit_action", "mechanic_attendance_audit", ["action"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_mechanic_attendance_audit_action", table_name="mechanic_attendance_audit")
    op.drop_index("ix_mechanic_attendance_audit_actor_user_id", table_name="mechanic_attendance_audit")
    op.drop_index("ix_mechanic_attendance_audit_mechanic_id", table_name="mechanic_attendance_audit")
    op.drop_index("ix_mechanic_attendance_audit_break_session_id", table_name="mechanic_attendance_audit")
    op.drop_index("ix_mechanic_attendance_audit_attendance_session_id", table_name="mechanic_attendance_audit")
    op.drop_index("ix_mechanic_attendance_audit_tenant_id", table_name="mechanic_attendance_audit")
    op.drop_table("mechanic_attendance_audit")

    op.drop_index("uq_mechanic_break_sessions_active_mechanic", table_name="mechanic_break_sessions")
    op.drop_index("ix_mechanic_break_sessions_ended_by_user_id", table_name="mechanic_break_sessions")
    op.drop_index("ix_mechanic_break_sessions_started_by_user_id", table_name="mechanic_break_sessions")
    op.drop_index("ix_mechanic_break_sessions_ended_at", table_name="mechanic_break_sessions")
    op.drop_index("ix_mechanic_break_sessions_started_at", table_name="mechanic_break_sessions")
    op.drop_index("ix_mechanic_break_sessions_attendance_session_id", table_name="mechanic_break_sessions")
    op.drop_index("ix_mechanic_break_sessions_mechanic_id", table_name="mechanic_break_sessions")
    op.drop_index("ix_mechanic_break_sessions_tenant_id", table_name="mechanic_break_sessions")
    op.drop_table("mechanic_break_sessions")

    op.drop_index("uq_mechanic_attendance_sessions_active_mechanic", table_name="mechanic_attendance_sessions")
    op.drop_index("ix_mechanic_attendance_sessions_ended_by_user_id", table_name="mechanic_attendance_sessions")
    op.drop_index("ix_mechanic_attendance_sessions_started_by_user_id", table_name="mechanic_attendance_sessions")
    op.drop_index("ix_mechanic_attendance_sessions_ended_at", table_name="mechanic_attendance_sessions")
    op.drop_index("ix_mechanic_attendance_sessions_started_at", table_name="mechanic_attendance_sessions")
    op.drop_index("ix_mechanic_attendance_sessions_local_date", table_name="mechanic_attendance_sessions")
    op.drop_index("ix_mechanic_attendance_sessions_mechanic_id", table_name="mechanic_attendance_sessions")
    op.drop_index("ix_mechanic_attendance_sessions_tenant_id", table_name="mechanic_attendance_sessions")
    op.drop_table("mechanic_attendance_sessions")

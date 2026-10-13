"""Add operation execution and immutable timer attribution without backfilling work."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
revision = "168_operation_execution"
down_revision = "167_merge_checklist_conversion"
branch_labels = None
depends_on = None

def upgrade():
    op.add_column("labor", sa.Column("execution_status", sa.String(16), nullable=True))
    op.add_column("labor", sa.Column("execution_version", sa.Integer(), server_default="0", nullable=False))
    op.add_column("labor", sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("labor", sa.Column("completed_by_user_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True))
    op.add_column("labor", sa.Column("completed_by_name", sa.String(255), nullable=True))
    op.create_check_constraint("ck_labor_execution_status", "labor", "execution_status IS NULL OR execution_status IN ('pending', 'completed')")
    op.create_check_constraint("ck_labor_execution_version", "labor", "execution_version >= 0")
    op.add_column("mechanic_time_sessions", sa.Column("labor_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("labor.id", ondelete="SET NULL"), nullable=True))
    op.add_column("mechanic_time_sessions", sa.Column("labor_id_snapshot", postgresql.UUID(as_uuid=True), nullable=True))
    op.add_column("mechanic_time_sessions", sa.Column("labor_description_snapshot", sa.Text(), nullable=True))
    op.create_index("ix_mechanic_time_sessions_labor_id", "mechanic_time_sessions", ["labor_id"])
    op.create_index("ix_mechanic_time_sessions_labor_id_snapshot", "mechanic_time_sessions", ["labor_id_snapshot"])
    op.create_check_constraint("ck_timer_operation_type", "mechanic_time_sessions", "labor_id_snapshot IS NULL OR (session_type = 'repair_order' AND repair_order_id IS NOT NULL)")

def downgrade():
    op.drop_constraint("ck_timer_operation_type", "mechanic_time_sessions", type_="check")
    for name in ("labor_description_snapshot", "labor_id_snapshot", "labor_id"):
        op.drop_column("mechanic_time_sessions", name)
    op.drop_constraint("ck_labor_execution_status", "labor", type_="check")
    op.drop_constraint("ck_labor_execution_version", "labor", type_="check")
    for name in ("completed_by_name", "completed_by_user_id", "completed_at", "execution_version", "execution_status"):
        op.drop_column("labor", name)

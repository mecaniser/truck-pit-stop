"""Staff planned start and promised finish, independent of execution timestamps."""
from alembic import op
import sqlalchemy as sa

revision = "173_repair_order_schedule"
down_revision = "172_external_service_receipts"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("repair_orders", sa.Column("scheduled_start_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("repair_orders", sa.Column("promised_finish_at", sa.DateTime(timezone=True), nullable=True))
    op.create_check_constraint("ck_repair_orders_schedule_order", "repair_orders",
                               "scheduled_start_at IS NULL OR promised_finish_at IS NULL OR promised_finish_at > scheduled_start_at")
    op.create_index("ix_repair_orders_tenant_promised_finish", "repair_orders",
                    ["tenant_id", "promised_finish_at", "id"],
                    postgresql_where=sa.text("promised_finish_at IS NOT NULL"))


def downgrade():
    # Disposable migration verification only; application rollbacks retain dates.
    op.drop_index("ix_repair_orders_tenant_promised_finish", table_name="repair_orders")
    op.drop_constraint("ck_repair_orders_schedule_order", "repair_orders", type_="check")
    op.drop_column("repair_orders", "promised_finish_at")
    op.drop_column("repair_orders", "scheduled_start_at")

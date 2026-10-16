"""Current source contact evidence, separate from editable customer fields."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "175_customer_contact_snapshot"
down_revision = "174_parts_pricing_matrix"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("customers", sa.Column("ets_contact_phone_snapshot", postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column("customers", "ets_contact_phone_snapshot")

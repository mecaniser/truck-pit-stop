"""Add nullable ETS provenance, separate from settlement evidence."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "171_ets_source_evidence"
down_revision = "170_shop_history_cursor"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("invoices", sa.Column("ets_source_evidence", postgresql.JSONB(), nullable=True))


def downgrade():
    op.drop_column("invoices", "ets_source_evidence")

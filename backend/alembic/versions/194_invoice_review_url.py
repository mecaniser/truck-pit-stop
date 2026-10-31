"""Add an optional shop review link for customer invoices."""
from alembic import op
import sqlalchemy as sa

revision = "194_invoice_review_url"
down_revision = "193_vehicle_equipment_type"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("tenants", sa.Column("review_url", sa.String(2048), nullable=True))


def downgrade():
    op.drop_column("tenants", "review_url")

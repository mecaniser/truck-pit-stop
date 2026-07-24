"""merge invoice reminder and QuickBooks migration heads

Revision ID: 105_merge_invoice_qb_heads
Revises: 018, 104_qb_webhook_deleted_at
"""


# revision identifiers, used by Alembic.
revision = "105_merge_invoice_qb_heads"
down_revision = ("018", "104_qb_webhook_deleted_at")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Join migration histories without changing schema or data."""


def downgrade() -> None:
    """Keep both parent histories intact when rolling back."""

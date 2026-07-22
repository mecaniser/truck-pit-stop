"""merge repair-order projection and invoice-payment migration heads

Revision ID: 098_merge_repair_invoice_heads
Revises: 096_repair_order_read_model, 097_manual_payment_evidence
"""


revision = "098_merge_repair_invoice_heads"
down_revision = ("096_repair_order_read_model", "097_manual_payment_evidence")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This revision only joins independently merged schema branches.
    pass


def downgrade() -> None:
    pass

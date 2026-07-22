"""merge invoice and vehicle-relationship migration heads

Revision ID: 100_merge_invoice_vehicle_heads
Revises: 099_invoice_read_model, 099_vehicle_relationships
"""


revision = "100_merge_invoice_vehicle_heads"
down_revision = ("099_invoice_read_model", "099_vehicle_relationships")
branch_labels = None
depends_on = None


def upgrade() -> None:
    # This revision only joins independently merged schema branches.
    pass


def downgrade() -> None:
    pass

"""merge WorkOS identity and customer balance migration heads

Revision ID: 113_merge_identity_balance
Revises: 112_identity_membership, 111_customer_balance
"""


revision = "113_merge_identity_balance"
down_revision = ("112_identity_membership", "111_customer_balance")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass

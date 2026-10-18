"""Join the independent SMS and dashboard binding migration branches.

Revision ID: 180_sms_dashboard_merge
Revises: 179_multishop_sms, 177_dashboard_bindings
"""

revision = "180_sms_dashboard_merge"
down_revision = ("179_multishop_sms", "177_dashboard_bindings")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass

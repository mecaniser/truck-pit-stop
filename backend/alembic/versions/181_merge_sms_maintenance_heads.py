"""Join independently released maintenance and SMS migration families.

Preserves every existing migration and adds no schema or data mutations.
"""

revision = "181_sms_maintenance_merge"
down_revision = ("180_sms_dashboard_merge", "178_merge_maintenance_bindings")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass

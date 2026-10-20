"""Join independently reviewed receivables and released SMS/maintenance heads.

Preserve both migration families without changing schema or financial rows.
"""

revision = "182_receivables_sms_merge"
down_revision = ("179_db135_receivables", "181_sms_maintenance_merge")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass

"""Join reviewed receivables with released CallRail migration history.

Graph only: preserve both families without changing schema or financial rows.
"""

revision = "184_db135_callrail_merge"
down_revision = ("182_receivables_sms_merge", "183_callrail_reply_routes")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass

"""Join customer-free CallRail inquiries with released receivables history.

Graph only: retain both migration families without schema or data mutations.
"""
revision = '185_callrail_inquiry_main_merge'
down_revision = ('184_callrail_inquiries', '184_db135_callrail_merge')
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass

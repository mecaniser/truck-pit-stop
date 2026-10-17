"""Join contact evidence and customer pricing without rewriting applied history.

Both feature revisions descend from 174_parts_pricing_matrix. Applying this
no-op merge runs only the missing branch for each environment, preserving
populated customer-pricing previews and production contact evidence.
"""

revision = "176_merge_contact_pricing"
down_revision = (
    "175_customer_contact_snapshot",
    "175_customer_pricing_defaults",
)
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass

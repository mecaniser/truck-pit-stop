"""merge Google Reviews and repair-authorization migration heads

Revision ID: 107_merge_reviews_authorizations
Revises: 106_google_reviews, 106_versioned_authorizations
"""


# revision identifiers, used by Alembic.
revision = "107_merge_reviews_authorizations"
down_revision = ("106_google_reviews", "106_versioned_authorizations")
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Join independent schema branches without changing schema or data."""


def downgrade() -> None:
    """Keep both parent histories intact when rolling back."""

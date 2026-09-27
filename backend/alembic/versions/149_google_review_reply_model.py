"""DB-086: per-tenant Claude model for Google review reply drafts; NULL means the platform default."""
from alembic import op
import sqlalchemy as sa

revision = "149_google_review_reply_model"
down_revision = "148_elis_outcome_source"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("google_review_settings", sa.Column("reply_model", sa.String(length=64), nullable=True))


def downgrade():
    op.drop_column("google_review_settings", "reply_model")

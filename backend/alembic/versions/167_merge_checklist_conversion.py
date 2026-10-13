"""Combine independently reviewed checklist and recommendation preview migrations.

Integration-only ancestry: no schema operations. Both feature migrations must
be retained when these branches are integrated for a release.
"""
revision = "167_merge_checklist_conversion"
down_revision = ("165_service_checklists", "166_recommendation_conversion")
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass

"""add fleet incident photos

Revision ID: 076
Revises: 075
Create Date: 2026-07-14
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "076"
down_revision = "075"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "fleet_incident_photos",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("tenant_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("tenants.id"), nullable=False),
        sa.Column("incident_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("fleet_incidents.id", ondelete="CASCADE"), nullable=False),
        sa.Column("uploaded_by_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("image_url", sa.String(length=500), nullable=False),
        sa.Column("cloudinary_public_id", sa.String(length=255), nullable=True),
        sa.Column("caption", sa.String(length=500), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_fleet_incident_photos_tenant_id", "fleet_incident_photos", ["tenant_id"])
    op.create_index("ix_fleet_incident_photos_incident_id", "fleet_incident_photos", ["incident_id"])
    op.create_index("ix_fleet_incident_photos_uploaded_by_id", "fleet_incident_photos", ["uploaded_by_id"])


def downgrade() -> None:
    op.drop_index("ix_fleet_incident_photos_uploaded_by_id", table_name="fleet_incident_photos")
    op.drop_index("ix_fleet_incident_photos_incident_id", table_name="fleet_incident_photos")
    op.drop_index("ix_fleet_incident_photos_tenant_id", table_name="fleet_incident_photos")
    op.drop_table("fleet_incident_photos")

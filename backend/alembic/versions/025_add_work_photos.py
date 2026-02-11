"""Add work_photos table for mechanic photo uploads

Revision ID: 025
Revises: 024
Create Date: 2026-02-07
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers
revision = '025'
down_revision = '024'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'work_photos',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('repair_order_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('mechanic_id', postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column('image_url', sa.String(500), nullable=False),
        sa.Column('cloudinary_public_id', sa.String(255), nullable=True),
        sa.Column('caption', sa.String(500), nullable=True),
        sa.Column('uploaded_at', sa.DateTime(), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=True),
        sa.Column('updated_at', sa.DateTime(), nullable=True),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['repair_order_id'], ['repair_orders.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['mechanic_id'], ['users.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index('ix_work_photos_repair_order_id', 'work_photos', ['repair_order_id'])
    op.create_index('ix_work_photos_mechanic_id', 'work_photos', ['mechanic_id'])


def downgrade() -> None:
    op.drop_index('ix_work_photos_mechanic_id', table_name='work_photos')
    op.drop_index('ix_work_photos_repair_order_id', table_name='work_photos')
    op.drop_table('work_photos')

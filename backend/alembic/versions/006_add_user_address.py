"""add user address

Revision ID: 006
Revises: 005
Create Date: 2024-XX-XX
"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '006'
down_revision = '005'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('users', sa.Column('address', sa.String(length=255), nullable=True))


def downgrade() -> None:
    op.drop_column('users', 'address')

"""split_user_name_fields

Revision ID: 003
Revises: 002
Create Date: 2025-12-12

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '003'
down_revision: Union[str, None] = '002'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add new columns (nullable initially for data migration)
    op.add_column('users', sa.Column('first_name', sa.String(100), nullable=True))
    op.add_column('users', sa.Column('last_name', sa.String(100), nullable=True))
    
    # Migrate data: split full_name into first_name/last_name
    op.execute("""
        UPDATE users
        SET 
            first_name = COALESCE(SPLIT_PART(full_name, ' ', 1), 'Unknown'),
            last_name = COALESCE(
                CASE 
                    WHEN POSITION(' ' IN COALESCE(full_name, '')) > 0 
                    THEN SUBSTRING(full_name FROM POSITION(' ' IN full_name) + 1)
                    ELSE 'Unknown'
                END,
                'Unknown'
            )
    """)
    
    # Handle any nulls from users without full_name
    op.execute("UPDATE users SET first_name = 'Unknown' WHERE first_name IS NULL OR first_name = ''")
    op.execute("UPDATE users SET last_name = 'Unknown' WHERE last_name IS NULL OR last_name = ''")
    
    # Make columns non-nullable
    op.alter_column('users', 'first_name', nullable=False)
    op.alter_column('users', 'last_name', nullable=False)
    
    # Drop old column
    op.drop_column('users', 'full_name')


def downgrade() -> None:
    # Add back full_name
    op.add_column('users', sa.Column('full_name', sa.String(255), nullable=True))
    
    # Merge first_name + last_name back
    op.execute("UPDATE users SET full_name = first_name || ' ' || last_name")
    
    # Drop new columns
    op.drop_column('users', 'first_name')
    op.drop_column('users', 'last_name')

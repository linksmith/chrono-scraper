"""Add LangExtract fields to projects table

Revision ID: add_langextract_fields
Revises: 
Create Date: 2025-08-13 04:58:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'add_langextract_fields'
down_revision = None  # Update this to the last migration ID
branch_labels = None
depends_on = None


def upgrade() -> None:
    """Add LangExtract configuration fields to projects table"""
    
    # Add new columns
    op.add_column('projects', sa.Column('langextract_enabled', sa.Boolean(), nullable=False, server_default='false'))
    op.add_column('projects', sa.Column('langextract_provider', sa.String(length=20), nullable=False, server_default='disabled'))
    op.add_column('projects', sa.Column('langextract_model', sa.String(length=100), nullable=True))
    op.add_column('projects', sa.Column('langextract_estimated_cost_per_1k', sa.Float(), nullable=True))


def downgrade() -> None:
    """Remove LangExtract configuration fields from projects table"""
    
    # Remove columns
    op.drop_column('projects', 'langextract_estimated_cost_per_1k')
    op.drop_column('projects', 'langextract_model')
    op.drop_column('projects', 'langextract_provider')
    op.drop_column('projects', 'langextract_enabled')
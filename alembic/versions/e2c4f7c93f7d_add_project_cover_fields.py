"""add project cover fields

Revision ID: e2c4f7c93f7d
Revises: 9f5ab90ded4a
Create Date: 2026-05-04 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "e2c4f7c93f7d"
down_revision = "9f5ab90ded4a"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("cover_path", sa.Text(), nullable=True))
    op.add_column("projects", sa.Column("cover_url", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "cover_url")
    op.drop_column("projects", "cover_path")

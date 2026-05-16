"""add project visibility

Revision ID: f13a6f4d9b21
Revises: e2c4f7c93f7d
Create Date: 2026-05-16 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "f13a6f4d9b21"
down_revision = "e2c4f7c93f7d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("visibility", sa.String(length=32), nullable=False, server_default="private"),
    )
    op.create_index(op.f("ix_projects_visibility"), "projects", ["visibility"], unique=False)
    op.execute("UPDATE projects SET visibility = 'public'")
    op.alter_column("projects", "visibility", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_projects_visibility"), table_name="projects")
    op.drop_column("projects", "visibility")

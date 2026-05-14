"""add asset folders

Revision ID: 5b0f8c1a2d34
Revises: e2c4f7c93f7d
Create Date: 2026-05-14 00:00:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "5b0f8c1a2d34"
down_revision = "e2c4f7c93f7d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "asset_folders",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("parent_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["parent_id"], ["asset_folders.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_asset_folders_project_id"), "asset_folders", ["project_id"], unique=False)
    op.create_index(op.f("ix_asset_folders_parent_id"), "asset_folders", ["parent_id"], unique=False)

    op.add_column("assets", sa.Column("folder_id", sa.Integer(), nullable=True))
    op.create_index(op.f("ix_assets_folder_id"), "assets", ["folder_id"], unique=False)
    op.create_foreign_key("fk_assets_folder_id_asset_folders", "assets", "asset_folders", ["folder_id"], ["id"])


def downgrade() -> None:
    op.drop_constraint("fk_assets_folder_id_asset_folders", "assets", type_="foreignkey")
    op.drop_index(op.f("ix_assets_folder_id"), table_name="assets")
    op.drop_column("assets", "folder_id")

    op.drop_index(op.f("ix_asset_folders_parent_id"), table_name="asset_folders")
    op.drop_index(op.f("ix_asset_folders_project_id"), table_name="asset_folders")
    op.drop_table("asset_folders")

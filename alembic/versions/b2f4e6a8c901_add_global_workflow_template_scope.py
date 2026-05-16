"""add global workflow template scope

Revision ID: b2f4e6a8c901
Revises: c4d8e1b2a9f0
Create Date: 2026-05-16 17:10:00.000000
"""

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = "b2f4e6a8c901"
down_revision = "c4d8e1b2a9f0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "workflow_templates",
        sa.Column("scope", sa.String(length=16), nullable=True, server_default=sa.text("'project'")),
    )
    op.execute("UPDATE workflow_templates SET scope = 'project' WHERE scope IS NULL")
    op.alter_column("workflow_templates", "scope", nullable=False, server_default=sa.text("'project'"))
    op.alter_column("workflow_templates", "project_id", existing_type=sa.Integer(), nullable=True)
    op.drop_constraint("uq_workflow_template_project_name", "workflow_templates", type_="unique")
    op.create_unique_constraint(
        "uq_workflow_template_scope_project_name",
        "workflow_templates",
        ["scope", "project_id", "name"],
    )
    op.create_index(op.f("ix_workflow_templates_scope"), "workflow_templates", ["scope"], unique=False)


def downgrade() -> None:
    op.execute("DELETE FROM workflow_templates WHERE scope = 'global'")
    op.drop_index(op.f("ix_workflow_templates_scope"), table_name="workflow_templates")
    op.drop_constraint("uq_workflow_template_scope_project_name", "workflow_templates", type_="unique")
    op.create_unique_constraint(
        "uq_workflow_template_project_name",
        "workflow_templates",
        ["project_id", "name"],
    )
    op.alter_column("workflow_templates", "project_id", existing_type=sa.Integer(), nullable=False)
    op.drop_column("workflow_templates", "scope")

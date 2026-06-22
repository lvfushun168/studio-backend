"""add legacy stage-level scene steps

Revision ID: 3a1f7c9d2e44
Revises: b2f4e6a8c901
Create Date: 2026-06-01 00:00:00.000000

This revision existed in the trial database but its migration source was not
present in the repository. It is reconstructed from the live schema so the
Alembic chain remains reproducible. PRD6 deliberately does not reuse this
legacy stage-level table for fine-grained work steps.
"""

from alembic import op
import sqlalchemy as sa


revision = "3a1f7c9d2e44"
down_revision = "b2f4e6a8c901"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "scene_steps",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("scene_id", sa.Integer(), sa.ForeignKey("scenes.id"), nullable=False),
        sa.Column("stage_progress_id", sa.Integer(), sa.ForeignKey("stage_progresses.id"), nullable=True),
        sa.Column("stage_key", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("assignee_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("rejected_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("scene_id", "stage_key", name="uq_scene_step_scene_stage"),
    )
    for column in ("project_id", "scene_id", "stage_progress_id", "stage_key", "status", "assignee_id"):
        op.create_index(f"ix_scene_steps_{column}", "scene_steps", [column])


def downgrade() -> None:
    op.drop_table("scene_steps")

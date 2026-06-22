"""add PRD6 work step models and production fields

Revision ID: d6f1a2b3c4e5
Revises: 3a1f7c9d2e44
Create Date: 2026-06-22 19:45:00.000000

Backup requirement: run pg_dump before applying this migration.
Summary: adds work-step templates, scene work steps, submissions, submission
assets and events; extends assets and stage_progresses with PRD6 fields.
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "d6f1a2b3c4e5"
down_revision = "3a1f7c9d2e44"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "work_step_templates",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("scope", sa.String(16), nullable=False),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=True),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("stage_key", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False, server_default=sa.text("1")),
        sa.Column("is_default", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "scope", "project_id", "stage_key", "name", "version",
            name="uq_work_step_template_scope_project_stage_name_version",
        ),
    )
    op.create_index("ix_work_step_templates_scope", "work_step_templates", ["scope"])
    op.create_index("ix_work_step_templates_stage_key", "work_step_templates", ["stage_key"])
    op.create_index("ix_work_step_templates_project_stage_active", "work_step_templates", ["project_id", "stage_key", "is_active"])
    op.create_index("ix_work_step_templates_scope_stage_default", "work_step_templates", ["scope", "stage_key", "is_default"])

    op.create_table(
        "work_step_template_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("template_id", sa.BigInteger(), sa.ForeignKey("work_step_templates.id", ondelete="CASCADE"), nullable=False),
        sa.Column("step_key", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_parallel", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("default_duration_hours", sa.Numeric(8, 2), nullable=True),
        sa.Column("default_role", sa.String(32), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("template_id", "step_key", name="uq_work_step_template_item_key"),
    )
    op.create_index("ix_work_step_template_items_template_id", "work_step_template_items", ["template_id"])

    op.add_column("stage_progresses", sa.Column("assignee_id", sa.Integer(), nullable=True))
    op.add_column("stage_progresses", sa.Column("due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("stage_progresses", sa.Column("priority", sa.String(16), nullable=False, server_default=sa.text("'normal'")))
    op.add_column("stage_progresses", sa.Column("blocked_reason", sa.String(64), nullable=True))
    op.add_column("stage_progresses", sa.Column("production_note", sa.Text(), nullable=True))
    op.create_foreign_key("fk_stage_progresses_assignee_id_users", "stage_progresses", "users", ["assignee_id"], ["id"])
    op.create_index("ix_stage_progresses_assignee_id", "stage_progresses", ["assignee_id"])

    op.create_table(
        "scene_work_steps",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("scene_group_id", sa.Integer(), sa.ForeignKey("scene_groups.id"), nullable=False),
        sa.Column("scene_id", sa.Integer(), sa.ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_progress_id", sa.Integer(), sa.ForeignKey("stage_progresses.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_key", sa.String(64), nullable=False),
        sa.Column("template_id", sa.BigInteger(), sa.ForeignKey("work_step_templates.id", ondelete="SET NULL"), nullable=True),
        sa.Column("template_item_id", sa.BigInteger(), sa.ForeignKey("work_step_template_items.id", ondelete="SET NULL"), nullable=True),
        sa.Column("step_key", sa.String(64), nullable=False),
        sa.Column("name", sa.String(128), nullable=False),
        sa.Column("original_name", sa.String(128), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_required", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("allow_parallel", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("assignee_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("priority", sa.String(16), nullable=False, server_default=sa.text("'normal'")),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("blocked_reason", sa.String(64), nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("scene_id", "stage_key", "step_key", name="uq_scene_work_step"),
    )
    for column in ("project_id", "scene_group_id", "scene_id", "stage_progress_id", "stage_key", "status", "assignee_id", "due_at", "blocked_reason"):
        op.create_index(f"ix_scene_work_steps_{column}", "scene_work_steps", [column])
    op.create_index("ix_scene_work_steps_project_stage_status", "scene_work_steps", ["project_id", "stage_key", "status"])
    op.create_index("ix_scene_work_steps_assignee_status_due", "scene_work_steps", ["assignee_id", "status", "due_at"])
    op.create_index("ix_scene_work_steps_scene_stage_sort", "scene_work_steps", ["scene_id", "stage_key", "sort_order"])

    op.create_table(
        "step_submissions",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("scene_id", sa.Integer(), sa.ForeignKey("scenes.id"), nullable=False),
        sa.Column("scene_work_step_id", sa.BigInteger(), sa.ForeignKey("scene_work_steps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("stage_progress_id", sa.Integer(), sa.ForeignKey("stage_progresses.id"), nullable=False),
        sa.Column("stage_key", sa.String(64), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("submitted_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("reject_reason", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("scene_work_step_id", "version", name="uq_step_submission_version"),
    )
    for column in ("project_id", "scene_id", "scene_work_step_id", "stage_progress_id", "status"):
        op.create_index(f"ix_step_submissions_{column}", "step_submissions", [column])

    op.create_table(
        "step_submission_assets",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("submission_id", sa.BigInteger(), sa.ForeignKey("step_submissions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("asset_id", sa.Integer(), sa.ForeignKey("assets.id"), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default=sa.text("0")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("submission_id", "asset_id", name="uq_step_submission_asset"),
    )
    op.create_index("ix_step_submission_assets_submission_id", "step_submission_assets", ["submission_id"])
    op.create_index("ix_step_submission_assets_asset_id", "step_submission_assets", ["asset_id"])

    op.create_table(
        "work_step_events",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("project_id", sa.Integer(), sa.ForeignKey("projects.id"), nullable=False),
        sa.Column("scene_id", sa.Integer(), sa.ForeignKey("scenes.id"), nullable=False),
        sa.Column("scene_work_step_id", sa.BigInteger(), sa.ForeignKey("scene_work_steps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("operator_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False),
        sa.Column("action", sa.String(64), nullable=False),
        sa.Column("from_status", sa.String(32), nullable=True),
        sa.Column("to_status", sa.String(32), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    for column in ("project_id", "scene_id", "scene_work_step_id", "action"):
        op.create_index(f"ix_work_step_events_{column}", "work_step_events", [column])

    op.add_column("assets", sa.Column("scene_work_step_id", sa.BigInteger(), nullable=True))
    op.add_column("assets", sa.Column("asset_usage", sa.String(32), nullable=False, server_default=sa.text("'stage_asset'")))
    op.add_column("assets", sa.Column("lifecycle_status", sa.String(32), nullable=False, server_default=sa.text("'active'")))
    op.add_column("assets", sa.Column("is_invalid", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("assets", sa.Column("invalid_reason", sa.Text(), nullable=True))
    op.add_column("assets", sa.Column("invalidated_by", sa.Integer(), nullable=True))
    op.add_column("assets", sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True))
    op.create_foreign_key("fk_assets_scene_work_step_id", "assets", "scene_work_steps", ["scene_work_step_id"], ["id"], ondelete="SET NULL")
    op.create_foreign_key("fk_assets_invalidated_by_users", "assets", "users", ["invalidated_by"], ["id"])
    for column in ("scene_work_step_id", "asset_usage", "lifecycle_status", "is_invalid"):
        op.create_index(f"ix_assets_{column}", "assets", [column])

    # Existing trial data receives an independent default step per stage. New
    # scenes use template selection in the application transaction.
    op.execute(
        """
        INSERT INTO scene_work_steps (
            project_id, scene_group_id, scene_id, stage_progress_id, stage_key,
            step_key, name, original_name, sort_order, is_required,
            allow_parallel, status, priority, created_by
        )
        SELECT sp.project_id, s.scene_group_id, s.id, sp.id, sp.stage_key,
               'stage_delivery', '阶段交付', '阶段交付', 10, true,
               false, CASE WHEN sp.status = 'locked' THEN 'not_ready' ELSE 'todo' END,
               'normal', s.created_by
        FROM stage_progresses sp
        JOIN scenes s ON s.id = sp.scene_id
        WHERE NOT EXISTS (
            SELECT 1 FROM scene_work_steps sws
            WHERE sws.scene_id = sp.scene_id AND sws.stage_key = sp.stage_key
        )
        """
    )


def downgrade() -> None:
    for column in ("is_invalid", "lifecycle_status", "asset_usage", "scene_work_step_id"):
        op.drop_index(f"ix_assets_{column}", table_name="assets")
    op.drop_constraint("fk_assets_invalidated_by_users", "assets", type_="foreignkey")
    op.drop_constraint("fk_assets_scene_work_step_id", "assets", type_="foreignkey")
    for column in ("invalidated_at", "invalidated_by", "invalid_reason", "is_invalid", "lifecycle_status", "asset_usage", "scene_work_step_id"):
        op.drop_column("assets", column)

    op.drop_table("work_step_events")
    op.drop_table("step_submission_assets")
    op.drop_table("step_submissions")
    op.drop_table("scene_work_steps")
    op.drop_index("ix_stage_progresses_assignee_id", table_name="stage_progresses")
    op.drop_constraint("fk_stage_progresses_assignee_id_users", "stage_progresses", type_="foreignkey")
    for column in ("production_note", "blocked_reason", "priority", "due_at", "assignee_id"):
        op.drop_column("stage_progresses", column)
    op.drop_table("work_step_template_items")
    op.drop_table("work_step_templates")

"""Add admin and auth management tables.

Revision ID: 9f5ab90ded4a
Revises: 0adbb0da966d
Create Date: 2026-04-30 22:20:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = "9f5ab90ded4a"
down_revision = "0adbb0da966d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "auth_sessions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("token_hash", sa.String(length=128), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("user_agent", sa.Text(), nullable=True),
        sa.Column("ip_address", sa.String(length=128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_auth_sessions_token_hash"), "auth_sessions", ["token_hash"], unique=True)
    op.create_index(op.f("ix_auth_sessions_user_id"), "auth_sessions", ["user_id"], unique=False)

    op.create_table(
        "account_pool_accounts",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("last_check_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("fail_count", sa.Integer(), nullable=False),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("login_secret_encrypted", sa.Text(), nullable=True),
        sa.Column("extra_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_account_pool_accounts_email"), "account_pool_accounts", ["email"], unique=True)
    op.create_index(op.f("ix_account_pool_accounts_status"), "account_pool_accounts", ["status"], unique=False)

    op.create_table(
        "account_project_memberships",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("account_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["account_pool_accounts.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("account_id", "project_id", name="uq_account_project_membership"),
    )

    op.create_table(
        "prompt_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("aspect_ratio", sa.String(length=32), nullable=False),
        sa.Column("resolution", sa.String(length=32), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("use_count", sa.Integer(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_prompt_templates_project_id"), "prompt_templates", ["project_id"], unique=False)
    op.create_index(op.f("ix_prompt_templates_scope"), "prompt_templates", ["scope"], unique=False)
    op.create_index(op.f("ix_prompt_templates_user_id"), "prompt_templates", ["user_id"], unique=False)

    op.create_table(
        "image_groups",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("is_shared", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_image_groups_project_id"), "image_groups", ["project_id"], unique=False)
    op.create_index(op.f("ix_image_groups_user_id"), "image_groups", ["user_id"], unique=False)

    op.create_table(
        "image_group_images",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("image_group_id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["image_group_id"], ["image_groups.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_image_group_images_image_group_id"), "image_group_images", ["image_group_id"], unique=False)

    op.create_table(
        "generation_templates",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("created_by", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_generation_templates_project_id"), "generation_templates", ["project_id"], unique=False)
    op.create_index(op.f("ix_generation_templates_user_id"), "generation_templates", ["user_id"], unique=False)

    op.create_table(
        "generation_tasks",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("scene_id", sa.Integer(), nullable=True),
        sa.Column("stage_key", sa.String(length=64), nullable=True),
        sa.Column("account_id", sa.Integer(), nullable=True),
        sa.Column("image_group_id", sa.Integer(), nullable=True),
        sa.Column("prompt_id", sa.Integer(), nullable=True),
        sa.Column("prompt_content", sa.Text(), nullable=False),
        sa.Column("aspect_ratio", sa.String(length=32), nullable=False),
        sa.Column("resolution", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("requested_count", sa.Integer(), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("fail_reason", sa.Text(), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["account_id"], ["account_pool_accounts.id"]),
        sa.ForeignKeyConstraint(["image_group_id"], ["image_groups.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompt_templates.id"]),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_generation_tasks_account_id"), "generation_tasks", ["account_id"], unique=False)
    op.create_index(op.f("ix_generation_tasks_image_group_id"), "generation_tasks", ["image_group_id"], unique=False)
    op.create_index(op.f("ix_generation_tasks_project_id"), "generation_tasks", ["project_id"], unique=False)
    op.create_index(op.f("ix_generation_tasks_prompt_id"), "generation_tasks", ["prompt_id"], unique=False)
    op.create_index(op.f("ix_generation_tasks_scene_id"), "generation_tasks", ["scene_id"], unique=False)
    op.create_index(op.f("ix_generation_tasks_status"), "generation_tasks", ["status"], unique=False)
    op.create_index(op.f("ix_generation_tasks_user_id"), "generation_tasks", ["user_id"], unique=False)

    op.create_table(
        "generation_results",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("task_id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("project_id", sa.Integer(), nullable=False),
        sa.Column("scene_id", sa.Integer(), nullable=True),
        sa.Column("stage_key", sa.String(length=64), nullable=True),
        sa.Column("image_group_id", sa.Integer(), nullable=True),
        sa.Column("prompt_id", sa.Integer(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("thumbnail_url", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("review_comment", sa.Text(), nullable=True),
        sa.Column("reviewed_by", sa.Integer(), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["image_group_id"], ["image_groups.id"]),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["prompt_id"], ["prompt_templates.id"]),
        sa.ForeignKeyConstraint(["reviewed_by"], ["users.id"]),
        sa.ForeignKeyConstraint(["scene_id"], ["scenes.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["generation_tasks.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_generation_results_image_group_id"), "generation_results", ["image_group_id"], unique=False)
    op.create_index(op.f("ix_generation_results_project_id"), "generation_results", ["project_id"], unique=False)
    op.create_index(op.f("ix_generation_results_prompt_id"), "generation_results", ["prompt_id"], unique=False)
    op.create_index(op.f("ix_generation_results_scene_id"), "generation_results", ["scene_id"], unique=False)
    op.create_index(op.f("ix_generation_results_status"), "generation_results", ["status"], unique=False)
    op.create_index(op.f("ix_generation_results_task_id"), "generation_results", ["task_id"], unique=False)
    op.create_index(op.f("ix_generation_results_user_id"), "generation_results", ["user_id"], unique=False)

    op.create_table(
        "audit_logs",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("user_id", sa.Integer(), nullable=True),
        sa.Column("project_id", sa.Integer(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("target_type", sa.String(length=64), nullable=False),
        sa.Column("target_id", sa.Integer(), nullable=True),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("payload_json", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_audit_logs_action"), "audit_logs", ["action"], unique=False)
    op.create_index(op.f("ix_audit_logs_project_id"), "audit_logs", ["project_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_target_id"), "audit_logs", ["target_id"], unique=False)
    op.create_index(op.f("ix_audit_logs_target_type"), "audit_logs", ["target_type"], unique=False)
    op.create_index(op.f("ix_audit_logs_user_id"), "audit_logs", ["user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_audit_logs_user_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_target_type"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_target_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_project_id"), table_name="audit_logs")
    op.drop_index(op.f("ix_audit_logs_action"), table_name="audit_logs")
    op.drop_table("audit_logs")

    op.drop_index(op.f("ix_generation_results_user_id"), table_name="generation_results")
    op.drop_index(op.f("ix_generation_results_task_id"), table_name="generation_results")
    op.drop_index(op.f("ix_generation_results_status"), table_name="generation_results")
    op.drop_index(op.f("ix_generation_results_scene_id"), table_name="generation_results")
    op.drop_index(op.f("ix_generation_results_prompt_id"), table_name="generation_results")
    op.drop_index(op.f("ix_generation_results_project_id"), table_name="generation_results")
    op.drop_index(op.f("ix_generation_results_image_group_id"), table_name="generation_results")
    op.drop_table("generation_results")

    op.drop_index(op.f("ix_generation_tasks_user_id"), table_name="generation_tasks")
    op.drop_index(op.f("ix_generation_tasks_status"), table_name="generation_tasks")
    op.drop_index(op.f("ix_generation_tasks_scene_id"), table_name="generation_tasks")
    op.drop_index(op.f("ix_generation_tasks_prompt_id"), table_name="generation_tasks")
    op.drop_index(op.f("ix_generation_tasks_project_id"), table_name="generation_tasks")
    op.drop_index(op.f("ix_generation_tasks_image_group_id"), table_name="generation_tasks")
    op.drop_index(op.f("ix_generation_tasks_account_id"), table_name="generation_tasks")
    op.drop_table("generation_tasks")

    op.drop_index(op.f("ix_generation_templates_user_id"), table_name="generation_templates")
    op.drop_index(op.f("ix_generation_templates_project_id"), table_name="generation_templates")
    op.drop_table("generation_templates")

    op.drop_index(op.f("ix_image_group_images_image_group_id"), table_name="image_group_images")
    op.drop_table("image_group_images")

    op.drop_index(op.f("ix_image_groups_user_id"), table_name="image_groups")
    op.drop_index(op.f("ix_image_groups_project_id"), table_name="image_groups")
    op.drop_table("image_groups")

    op.drop_index(op.f("ix_prompt_templates_user_id"), table_name="prompt_templates")
    op.drop_index(op.f("ix_prompt_templates_scope"), table_name="prompt_templates")
    op.drop_index(op.f("ix_prompt_templates_project_id"), table_name="prompt_templates")
    op.drop_table("prompt_templates")

    op.drop_table("account_project_memberships")
    op.drop_index(op.f("ix_account_pool_accounts_status"), table_name="account_pool_accounts")
    op.drop_index(op.f("ix_account_pool_accounts_email"), table_name="account_pool_accounts")
    op.drop_table("account_pool_accounts")

    op.drop_index(op.f("ix_auth_sessions_user_id"), table_name="auth_sessions")
    op.drop_index(op.f("ix_auth_sessions_token_hash"), table_name="auth_sessions")
    op.drop_table("auth_sessions")

    op.drop_column("users", "last_login_at")

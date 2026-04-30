"""Initial migration with all models.

Revision ID: 0adbb0da966d
Revises:
Create Date: 2026-04-30 11:05:56.562159
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision = '0adbb0da966d'
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        'users',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('username', sa.String(length=64), nullable=False),
        sa.Column('display_name', sa.String(length=128), nullable=False),
        sa.Column('email', sa.String(length=255), nullable=True),
        sa.Column('role', sa.String(length=32), nullable=False),
        sa.Column('password_hash', sa.String(length=255), nullable=True),
        sa.Column('api_key', sa.String(length=255), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_users_api_key'), 'users', ['api_key'], unique=False)
    op.create_index(op.f('ix_users_role'), 'users', ['role'], unique=False)
    op.create_index(op.f('ix_users_username'), 'users', ['username'], unique=True)

    op.create_table(
        'projects',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('project_type', sa.String(length=32), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('deadline_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_projects_status'), 'projects', ['status'], unique=False)

    op.create_table(
        'user_project_memberships',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('role_in_project', sa.String(length=32), nullable=True),
        sa.Column('joined_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('user_id', 'project_id', name='uq_user_project_membership'),
    )

    op.create_table(
        'episodes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('episode_number', sa.Integer(), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'episode_number', name='uq_project_episode_number'),
    )
    op.create_index(op.f('ix_episodes_project_id'), 'episodes', ['project_id'], unique=False)

    op.create_table(
        'scene_groups',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('episode_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['episode_id'], ['episodes.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_scene_groups_episode_id'), 'scene_groups', ['episode_id'], unique=False)
    op.create_index(op.f('ix_scene_groups_project_id'), 'scene_groups', ['project_id'], unique=False)

    op.create_table(
        'scenes',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('scene_group_id', sa.Integer(), nullable=False),
        sa.Column('base_scene_id', sa.Integer(), nullable=True),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('level', sa.String(length=4), nullable=False),
        sa.Column('stage_template', sa.String(length=64), nullable=False),
        sa.Column('pipeline', sa.String(length=32), nullable=False),
        sa.Column('frame_count', sa.Integer(), nullable=False),
        sa.Column('duration_seconds', sa.Numeric(precision=8, scale=2), nullable=True),
        sa.Column('sort_order', sa.Integer(), nullable=False),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['base_scene_id'], ['scenes.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['scene_group_id'], ['scene_groups.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('project_id', 'scene_group_id', 'name', name='uq_scene_name_in_group'),
    )
    op.create_index(op.f('ix_scenes_project_id'), 'scenes', ['project_id'], unique=False)
    op.create_index(op.f('ix_scenes_scene_group_id'), 'scenes', ['scene_group_id'], unique=False)
    op.create_index(op.f('ix_scenes_stage_template'), 'scenes', ['stage_template'], unique=False)

    op.create_table(
        'scene_assignments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('scene_id', sa.Integer(), nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('stage_key', sa.String(length=64), nullable=True),
        sa.Column('assigned_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['scene_id'], ['scenes.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scene_id', 'user_id', 'stage_key', name='uq_scene_assignment'),
    )

    op.create_table(
        'stage_progresses',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('scene_id', sa.Integer(), nullable=False),
        sa.Column('stage_key', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('reviewer_id', sa.Integer(), nullable=True),
        sa.Column('reviewed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('submitted_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('approved_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('rejected_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['reviewer_id'], ['users.id']),
        sa.ForeignKeyConstraint(['scene_id'], ['scenes.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scene_id', 'stage_key', name='uq_stage_progress_scene_stage'),
    )
    op.create_index(op.f('ix_stage_progresses_project_id'), 'stage_progresses', ['project_id'], unique=False)
    op.create_index(op.f('ix_stage_progresses_scene_id'), 'stage_progresses', ['scene_id'], unique=False)
    op.create_index(op.f('ix_stage_progresses_stage_key'), 'stage_progresses', ['stage_key'], unique=False)
    op.create_index(op.f('ix_stage_progresses_status'), 'stage_progresses', ['status'], unique=False)

    op.create_table(
        'assets',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('scene_group_id', sa.Integer(), nullable=True),
        sa.Column('scene_id', sa.Integer(), nullable=True),
        sa.Column('stage_key', sa.String(length=64), nullable=False),
        sa.Column('asset_type', sa.String(length=32), nullable=False),
        sa.Column('media_type', sa.String(length=16), nullable=False),
        sa.Column('bank_material_id', sa.Integer(), nullable=True),
        sa.Column('bank_reference_id', sa.Integer(), nullable=True),
        sa.Column('is_global', sa.Boolean(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('original_name', sa.String(length=255), nullable=False),
        sa.Column('extension', sa.String(length=32), nullable=True),
        sa.Column('storage_path', sa.Text(), nullable=False),
        sa.Column('public_url', sa.Text(), nullable=True),
        sa.Column('thumbnail_path', sa.Text(), nullable=True),
        sa.Column('thumbnail_url', sa.Text(), nullable=True),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('note', sa.Text(), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('uploaded_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['scene_group_id'], ['scene_groups.id']),
        sa.ForeignKeyConstraint(['scene_id'], ['scenes.id']),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_assets_original_name'), 'assets', ['original_name'], unique=False)
    op.create_index(op.f('ix_assets_project_id'), 'assets', ['project_id'], unique=False)
    op.create_index(op.f('ix_assets_scene_group_id'), 'assets', ['scene_group_id'], unique=False)
    op.create_index(op.f('ix_assets_scene_id'), 'assets', ['scene_id'], unique=False)
    op.create_index(op.f('ix_assets_stage_key'), 'assets', ['stage_key'], unique=False)

    op.create_table(
        'asset_attachments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('asset_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('media_type', sa.String(length=16), nullable=False),
        sa.Column('storage_path', sa.Text(), nullable=False),
        sa.Column('public_url', sa.Text(), nullable=True),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('uploaded_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['asset_id'], ['assets.id']),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_asset_attachments_asset_id'), 'asset_attachments', ['asset_id'], unique=False)

    op.create_table(
        'annotations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('target_asset_id', sa.Integer(), nullable=False),
        sa.Column('target_version', sa.Integer(), nullable=False),
        sa.Column('author_id', sa.Integer(), nullable=False),
        sa.Column('author_role', sa.String(length=32), nullable=False),
        sa.Column('frame_number', sa.Integer(), nullable=True),
        sa.Column('timestamp_seconds', sa.Numeric(precision=10, scale=3), nullable=True),
        sa.Column('canvas_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('overlay_path', sa.Text(), nullable=True),
        sa.Column('overlay_url', sa.Text(), nullable=True),
        sa.Column('merged_path', sa.Text(), nullable=True),
        sa.Column('merged_url', sa.Text(), nullable=True),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['author_id'], ['users.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['target_asset_id'], ['assets.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_annotations_author_id'), 'annotations', ['author_id'], unique=False)
    op.create_index(op.f('ix_annotations_frame_number'), 'annotations', ['frame_number'], unique=False)
    op.create_index(op.f('ix_annotations_project_id'), 'annotations', ['project_id'], unique=False)
    op.create_index(op.f('ix_annotations_target_asset_id'), 'annotations', ['target_asset_id'], unique=False)

    op.create_table(
        'annotation_attachments',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('annotation_id', sa.Integer(), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('media_type', sa.String(length=16), nullable=False),
        sa.Column('storage_path', sa.Text(), nullable=False),
        sa.Column('public_url', sa.Text(), nullable=True),
        sa.Column('size_bytes', sa.Integer(), nullable=True),
        sa.Column('uploaded_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['annotation_id'], ['annotations.id']),
        sa.ForeignKeyConstraint(['uploaded_by'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_annotation_attachments_annotation_id'), 'annotation_attachments', ['annotation_id'], unique=False)

    op.create_table(
        'async_jobs',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('job_type', sa.String(length=64), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('priority', sa.Integer(), nullable=False),
        sa.Column('payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('result_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('retry_count', sa.Integer(), nullable=False),
        sa.Column('max_retries', sa.Integer(), nullable=False),
        sa.Column('scheduled_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('finished_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_async_jobs_project_id'), 'async_jobs', ['project_id'], unique=False)
    op.create_index(op.f('ix_async_jobs_status'), 'async_jobs', ['status'], unique=False)

    op.create_table(
        'notifications',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=True),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('type', sa.String(length=64), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('content', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=16), nullable=False),
        sa.Column('payload_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('read_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_notifications_project_id'), 'notifications', ['project_id'], unique=False)
    op.create_index(op.f('ix_notifications_status'), 'notifications', ['status'], unique=False)
    op.create_index(op.f('ix_notifications_user_id'), 'notifications', ['user_id'], unique=False)

    op.create_table(
        'references',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('source_type', sa.String(length=32), nullable=False),
        sa.Column('source_id', sa.Integer(), nullable=False),
        sa.Column('target_type', sa.String(length=32), nullable=False),
        sa.Column('target_id', sa.Integer(), nullable=False),
        sa.Column('relation_type', sa.String(length=32), nullable=False),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_references_project_id'), 'references', ['project_id'], unique=False)
    op.create_index(op.f('ix_references_relation_type'), 'references', ['relation_type'], unique=False)
    op.create_index(op.f('ix_references_source_id'), 'references', ['source_id'], unique=False)
    op.create_index(op.f('ix_references_source_type'), 'references', ['source_type'], unique=False)
    op.create_index(op.f('ix_references_target_id'), 'references', ['target_id'], unique=False)
    op.create_index(op.f('ix_references_target_type'), 'references', ['target_type'], unique=False)

    op.create_table(
        'review_records',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('scene_id', sa.Integer(), nullable=False),
        sa.Column('stage_progress_id', sa.Integer(), nullable=False),
        sa.Column('stage_key', sa.String(length=64), nullable=False),
        sa.Column('action', sa.String(length=32), nullable=False),
        sa.Column('from_status', sa.String(length=32), nullable=True),
        sa.Column('to_status', sa.String(length=32), nullable=False),
        sa.Column('operator_id', sa.Integer(), nullable=False),
        sa.Column('comment', sa.Text(), nullable=True),
        sa.Column('extra_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['operator_id'], ['users.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['scene_id'], ['scenes.id']),
        sa.ForeignKeyConstraint(['stage_progress_id'], ['stage_progresses.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_review_records_project_id'), 'review_records', ['project_id'], unique=False)
    op.create_index(op.f('ix_review_records_scene_id'), 'review_records', ['scene_id'], unique=False)
    op.create_index(op.f('ix_review_records_stage_progress_id'), 'review_records', ['stage_progress_id'], unique=False)

    op.create_table(
        'bank_materials',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('source_asset_id', sa.Integer(), nullable=False),
        sa.Column('source_scene_id', sa.Integer(), nullable=False),
        sa.Column('source_stage_key', sa.String(length=64), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('character_name', sa.String(length=128), nullable=True),
        sa.Column('part_name', sa.String(length=128), nullable=True),
        sa.Column('pose', sa.String(length=128), nullable=True),
        sa.Column('angle', sa.String(length=128), nullable=True),
        sa.Column('current_asset_id', sa.Integer(), nullable=True),
        sa.Column('current_version', sa.Integer(), nullable=False),
        sa.Column('ref_count', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('metadata_json', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['current_asset_id'], ['assets.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['source_asset_id'], ['assets.id']),
        sa.ForeignKeyConstraint(['source_scene_id'], ['scenes.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_bank_materials_project_id'), 'bank_materials', ['project_id'], unique=False)

    op.create_table(
        'bank_references',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('bank_material_id', sa.Integer(), nullable=False),
        sa.Column('project_id', sa.Integer(), nullable=False),
        sa.Column('scene_id', sa.Integer(), nullable=False),
        sa.Column('stage_key', sa.String(length=64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False),
        sa.Column('detached_asset_id', sa.Integer(), nullable=True),
        sa.Column('created_by', sa.Integer(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['bank_material_id'], ['bank_materials.id']),
        sa.ForeignKeyConstraint(['created_by'], ['users.id']),
        sa.ForeignKeyConstraint(['detached_asset_id'], ['assets.id']),
        sa.ForeignKeyConstraint(['project_id'], ['projects.id']),
        sa.ForeignKeyConstraint(['scene_id'], ['scenes.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(op.f('ix_bank_references_bank_material_id'), 'bank_references', ['bank_material_id'], unique=False)
    op.create_index(op.f('ix_bank_references_project_id'), 'bank_references', ['project_id'], unique=False)
    op.create_index(op.f('ix_bank_references_scene_id'), 'bank_references', ['scene_id'], unique=False)
    op.create_index(op.f('ix_bank_references_status'), 'bank_references', ['status'], unique=False)

    op.create_foreign_key(
        'fk_assets_bank_material_id_bank_materials',
        'assets',
        'bank_materials',
        ['bank_material_id'],
        ['id'],
    )
    op.create_foreign_key(
        'fk_assets_bank_reference_id_bank_references',
        'assets',
        'bank_references',
        ['bank_reference_id'],
        ['id'],
    )


def downgrade() -> None:
    op.drop_constraint('fk_assets_bank_reference_id_bank_references', 'assets', type_='foreignkey')
    op.drop_constraint('fk_assets_bank_material_id_bank_materials', 'assets', type_='foreignkey')
    op.drop_index(op.f('ix_bank_references_status'), table_name='bank_references')
    op.drop_index(op.f('ix_bank_references_scene_id'), table_name='bank_references')
    op.drop_index(op.f('ix_bank_references_project_id'), table_name='bank_references')
    op.drop_index(op.f('ix_bank_references_bank_material_id'), table_name='bank_references')
    op.drop_table('bank_references')
    op.drop_index(op.f('ix_bank_materials_project_id'), table_name='bank_materials')
    op.drop_table('bank_materials')
    op.drop_index(op.f('ix_review_records_stage_progress_id'), table_name='review_records')
    op.drop_index(op.f('ix_review_records_scene_id'), table_name='review_records')
    op.drop_index(op.f('ix_review_records_project_id'), table_name='review_records')
    op.drop_table('review_records')
    op.drop_index(op.f('ix_references_target_type'), table_name='references')
    op.drop_index(op.f('ix_references_target_id'), table_name='references')
    op.drop_index(op.f('ix_references_source_type'), table_name='references')
    op.drop_index(op.f('ix_references_source_id'), table_name='references')
    op.drop_index(op.f('ix_references_relation_type'), table_name='references')
    op.drop_index(op.f('ix_references_project_id'), table_name='references')
    op.drop_table('references')
    op.drop_index(op.f('ix_notifications_user_id'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_status'), table_name='notifications')
    op.drop_index(op.f('ix_notifications_project_id'), table_name='notifications')
    op.drop_table('notifications')
    op.drop_index(op.f('ix_async_jobs_status'), table_name='async_jobs')
    op.drop_index(op.f('ix_async_jobs_project_id'), table_name='async_jobs')
    op.drop_table('async_jobs')
    op.drop_index(op.f('ix_annotation_attachments_annotation_id'), table_name='annotation_attachments')
    op.drop_table('annotation_attachments')
    op.drop_index(op.f('ix_annotations_target_asset_id'), table_name='annotations')
    op.drop_index(op.f('ix_annotations_project_id'), table_name='annotations')
    op.drop_index(op.f('ix_annotations_frame_number'), table_name='annotations')
    op.drop_index(op.f('ix_annotations_author_id'), table_name='annotations')
    op.drop_table('annotations')
    op.drop_index(op.f('ix_asset_attachments_asset_id'), table_name='asset_attachments')
    op.drop_table('asset_attachments')
    op.drop_index(op.f('ix_assets_stage_key'), table_name='assets')
    op.drop_index(op.f('ix_assets_scene_id'), table_name='assets')
    op.drop_index(op.f('ix_assets_scene_group_id'), table_name='assets')
    op.drop_index(op.f('ix_assets_project_id'), table_name='assets')
    op.drop_index(op.f('ix_assets_original_name'), table_name='assets')
    op.drop_table('assets')
    op.drop_index(op.f('ix_stage_progresses_status'), table_name='stage_progresses')
    op.drop_index(op.f('ix_stage_progresses_stage_key'), table_name='stage_progresses')
    op.drop_index(op.f('ix_stage_progresses_scene_id'), table_name='stage_progresses')
    op.drop_index(op.f('ix_stage_progresses_project_id'), table_name='stage_progresses')
    op.drop_table('stage_progresses')
    op.drop_table('scene_assignments')
    op.drop_index(op.f('ix_scenes_stage_template'), table_name='scenes')
    op.drop_index(op.f('ix_scenes_scene_group_id'), table_name='scenes')
    op.drop_index(op.f('ix_scenes_project_id'), table_name='scenes')
    op.drop_table('scenes')
    op.drop_index(op.f('ix_scene_groups_project_id'), table_name='scene_groups')
    op.drop_index(op.f('ix_scene_groups_episode_id'), table_name='scene_groups')
    op.drop_table('scene_groups')
    op.drop_index(op.f('ix_episodes_project_id'), table_name='episodes')
    op.drop_table('episodes')
    op.drop_table('user_project_memberships')
    op.drop_index(op.f('ix_projects_status'), table_name='projects')
    op.drop_table('projects')
    op.drop_index(op.f('ix_users_username'), table_name='users')
    op.drop_index(op.f('ix_users_role'), table_name='users')
    op.drop_index(op.f('ix_users_api_key'), table_name='users')
    op.drop_table('users')

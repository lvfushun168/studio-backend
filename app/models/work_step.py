from datetime import datetime
from decimal import Decimal

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, Numeric, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class WorkStepTemplate(TimestampMixin, Base):
    __tablename__ = "work_step_templates"
    __table_args__ = (
        UniqueConstraint(
            "scope", "project_id", "stage_key", "name", "version",
            name="uq_work_step_template_scope_project_stage_name_version",
        ),
        Index("ix_work_step_templates_project_stage_active", "project_id", "stage_key", "is_active"),
        Index("ix_work_step_templates_scope_stage_default", "scope", "stage_key", "is_default"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    scope: Mapped[str] = mapped_column(String(16), nullable=False, index=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    stage_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    is_default: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    items = relationship(
        "WorkStepTemplateItem",
        back_populates="template",
        cascade="all, delete-orphan",
        order_by="WorkStepTemplateItem.sort_order, WorkStepTemplateItem.id",
    )


class WorkStepTemplateItem(TimestampMixin, Base):
    __tablename__ = "work_step_template_items"
    __table_args__ = (
        UniqueConstraint("template_id", "step_key", name="uq_work_step_template_item_key"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("work_step_templates.id", ondelete="CASCADE"), nullable=False, index=True
    )
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_parallel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    default_duration_hours: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    default_role: Mapped[str | None] = mapped_column(String(32), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    template = relationship("WorkStepTemplate", back_populates="items")


class SceneWorkStep(TimestampMixin, Base):
    __tablename__ = "scene_work_steps"
    __table_args__ = (
        UniqueConstraint("scene_id", "stage_key", "step_key", name="uq_scene_work_step"),
        Index("ix_scene_work_steps_project_stage_status", "project_id", "stage_key", "status"),
        Index("ix_scene_work_steps_assignee_status_due", "assignee_id", "status", "due_at"),
        Index("ix_scene_work_steps_scene_stage_sort", "scene_id", "stage_key", "sort_order"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    scene_group_id: Mapped[int] = mapped_column(ForeignKey("scene_groups.id"), nullable=False, index=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id", ondelete="CASCADE"), nullable=False, index=True)
    stage_progress_id: Mapped[int] = mapped_column(
        ForeignKey("stage_progresses.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    template_id: Mapped[int | None] = mapped_column(
        ForeignKey("work_step_templates.id", ondelete="SET NULL"), nullable=True
    )
    template_item_id: Mapped[int | None] = mapped_column(
        ForeignKey("work_step_template_items.id", ondelete="SET NULL"), nullable=True
    )
    step_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    original_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    is_required: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    allow_parallel: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    assignee_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    priority: Mapped[str] = mapped_column(String(16), nullable=False, default="normal")
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)
    blocked_reason: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    submissions = relationship("StepSubmission", back_populates="work_step", cascade="all, delete-orphan")


class StepSubmission(TimestampMixin, Base):
    __tablename__ = "step_submissions"
    __table_args__ = (
        UniqueConstraint("scene_work_step_id", "version", name="uq_step_submission_version"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id"), nullable=False, index=True)
    scene_work_step_id: Mapped[int] = mapped_column(
        ForeignKey("scene_work_steps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    stage_progress_id: Mapped[int] = mapped_column(ForeignKey("stage_progresses.id"), nullable=False, index=True)
    stage_key: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    submitted_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reject_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)

    work_step = relationship("SceneWorkStep", back_populates="submissions")
    assets = relationship("StepSubmissionAsset", back_populates="submission", cascade="all, delete-orphan")


class StepSubmissionAsset(TimestampMixin, Base):
    __tablename__ = "step_submission_assets"
    __table_args__ = (
        UniqueConstraint("submission_id", "asset_id", name="uq_step_submission_asset"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    submission_id: Mapped[int] = mapped_column(
        ForeignKey("step_submissions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    submission = relationship("StepSubmission", back_populates="assets")


class WorkStepEvent(Base):
    __tablename__ = "work_step_events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id"), nullable=False, index=True)
    scene_work_step_id: Mapped[int] = mapped_column(
        ForeignKey("scene_work_steps.id", ondelete="CASCADE"), nullable=False, index=True
    )
    operator_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    from_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    to_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

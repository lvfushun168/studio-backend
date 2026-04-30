from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class Scene(TimestampMixin, Base):
    __tablename__ = "scenes"
    __table_args__ = (UniqueConstraint("project_id", "scene_group_id", "name", name="uq_scene_name_in_group"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    scene_group_id: Mapped[int] = mapped_column(ForeignKey("scene_groups.id"), nullable=False, index=True)
    base_scene_id: Mapped[int | None] = mapped_column(ForeignKey("scenes.id"), nullable=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    level: Mapped[str] = mapped_column(String(4), nullable=False)
    stage_template: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    pipeline: Mapped[str] = mapped_column(String(32), nullable=False)
    frame_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    duration_seconds: Mapped[float | None] = mapped_column(Numeric(8, 2), nullable=True)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    scene_group = relationship("SceneGroup", back_populates="scenes")
    stage_progresses = relationship("StageProgress", back_populates="scene", cascade="all, delete-orphan")
    assignments = relationship("SceneAssignment", back_populates="scene", cascade="all, delete-orphan")


class StageProgress(TimestampMixin, Base):
    __tablename__ = "stage_progresses"
    __table_args__ = (UniqueConstraint("scene_id", "stage_key", name="uq_stage_progress_scene_stage"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id"), nullable=False, index=True)
    stage_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    reviewer_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    scene = relationship("Scene", back_populates="stage_progresses")

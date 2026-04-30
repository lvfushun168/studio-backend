from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class Project(TimestampMixin, Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    project_type: Mapped[str] = mapped_column(String(32), default="series", nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False, index=True)
    deadline_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    memberships = relationship("UserProjectMembership", back_populates="project", cascade="all, delete-orphan")
    episodes = relationship("Episode", back_populates="project", cascade="all, delete-orphan")
    scene_groups = relationship("SceneGroup", back_populates="project", cascade="all, delete-orphan")

    @property
    def members(self):
        return self.memberships


class UserProjectMembership(Base):
    __tablename__ = "user_project_memberships"
    __table_args__ = (UniqueConstraint("user_id", "project_id", name="uq_user_project_membership"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False)
    role_in_project: Mapped[str | None] = mapped_column(String(32), nullable=True)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    user = relationship("User", back_populates="memberships")
    project = relationship("Project", back_populates="memberships")


class Episode(TimestampMixin, Base):
    __tablename__ = "episodes"
    __table_args__ = (UniqueConstraint("project_id", "episode_number", name="uq_project_episode_number"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    episode_number: Mapped[int] = mapped_column(Integer, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)

    project = relationship("Project", back_populates="episodes")
    scene_groups = relationship("SceneGroup", back_populates="episode")


class SceneGroup(TimestampMixin, Base):
    __tablename__ = "scene_groups"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    episode_id: Mapped[int | None] = mapped_column(ForeignKey("episodes.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    project = relationship("Project", back_populates="scene_groups")
    episode = relationship("Episode", back_populates="scene_groups")
    scenes = relationship("Scene", back_populates="scene_group", cascade="all, delete-orphan")


class SceneAssignment(Base):
    __tablename__ = "scene_assignments"
    __table_args__ = (UniqueConstraint("scene_id", "user_id", "stage_key", name="uq_scene_assignment"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    stage_key: Mapped[str | None] = mapped_column(String(64), nullable=True)
    assigned_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    scene = relationship("Scene", back_populates="assignments")

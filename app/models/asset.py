from datetime import datetime

from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class Asset(TimestampMixin, Base):
    __tablename__ = "assets"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    scene_group_id: Mapped[int | None] = mapped_column(ForeignKey("scene_groups.id"), nullable=True, index=True)
    scene_id: Mapped[int | None] = mapped_column(ForeignKey("scenes.id"), nullable=True, index=True)
    folder_id: Mapped[int | None] = mapped_column(ForeignKey("asset_folders.id"), nullable=True, index=True)
    stage_key: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    asset_type: Mapped[str] = mapped_column(String(32), default="original", nullable=False)
    media_type: Mapped[str] = mapped_column(String(16), nullable=False)
    bank_material_id: Mapped[int | None] = mapped_column(ForeignKey("bank_materials.id"), nullable=True)
    bank_reference_id: Mapped[int | None] = mapped_column(ForeignKey("bank_references.id"), nullable=True)
    is_global: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    original_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    extension: Mapped[str | None] = mapped_column(String(32), nullable=True)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    public_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    thumbnail_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    scene_work_step_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("scene_work_steps.id", ondelete="SET NULL"), nullable=True, index=True
    )
    asset_usage: Mapped[str] = mapped_column(String(32), nullable=False, default="stage_asset", index=True)
    lifecycle_status: Mapped[str] = mapped_column(String(32), nullable=False, default="active", index=True)
    is_invalid: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    invalid_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    invalidated_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    attachments = relationship("AssetAttachment", back_populates="asset", cascade="all, delete-orphan")
    folder = relationship("AssetFolder", back_populates="assets")


class AssetFolder(TimestampMixin, Base):
    __tablename__ = "asset_folders"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("asset_folders.id"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    parent = relationship("AssetFolder", remote_side=[id], back_populates="children")
    children = relationship("AssetFolder", back_populates="parent")
    assets = relationship("Asset", back_populates="folder")


class AssetAttachment(TimestampMixin, Base):
    __tablename__ = "asset_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    public_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    asset = relationship("Asset", back_populates="attachments")

from sqlalchemy import ForeignKey, Integer, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.models.mixins import TimestampMixin


class BankMaterial(TimestampMixin, Base):
    __tablename__ = "bank_materials"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    source_asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False)
    source_scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id"), nullable=False)
    source_stage_key: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    character_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    part_name: Mapped[str | None] = mapped_column(String(128), nullable=True)
    pose: Mapped[str | None] = mapped_column(String(128), nullable=True)
    angle: Mapped[str | None] = mapped_column(String(128), nullable=True)
    current_asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    current_version: Mapped[int] = mapped_column(Integer, nullable=False)
    ref_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="active", nullable=False)
    metadata_json: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    created_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)


class BankReference(TimestampMixin, Base):
    __tablename__ = "bank_references"

    id: Mapped[int] = mapped_column(primary_key=True)
    bank_material_id: Mapped[int] = mapped_column(ForeignKey("bank_materials.id"), nullable=False, index=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    scene_id: Mapped[int] = mapped_column(ForeignKey("scenes.id"), nullable=False, index=True)
    stage_key: Mapped[str] = mapped_column(String(64), nullable=False)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    detached_asset_id: Mapped[int | None] = mapped_column(ForeignKey("assets.id"), nullable=True)
    created_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

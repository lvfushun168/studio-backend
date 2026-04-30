from sqlalchemy import ForeignKey, Integer, Numeric, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.database import Base
from app.models.mixins import TimestampMixin


class Annotation(TimestampMixin, Base):
    __tablename__ = "annotations"

    id: Mapped[int] = mapped_column(primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"), nullable=False, index=True)
    target_asset_id: Mapped[int] = mapped_column(ForeignKey("assets.id"), nullable=False, index=True)
    target_version: Mapped[int] = mapped_column(Integer, nullable=False)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    author_role: Mapped[str] = mapped_column(String(32), nullable=False)
    frame_number: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    timestamp_seconds: Mapped[float | None] = mapped_column(Numeric(10, 3), nullable=True)
    canvas_json: Mapped[dict] = mapped_column(JSONB, nullable=False)
    overlay_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    overlay_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    merged_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    merged_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    attachments = relationship("AnnotationAttachment", back_populates="annotation", cascade="all, delete-orphan")


class AnnotationAttachment(TimestampMixin, Base):
    __tablename__ = "annotation_attachments"

    id: Mapped[int] = mapped_column(primary_key=True)
    annotation_id: Mapped[int] = mapped_column(ForeignKey("annotations.id"), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    media_type: Mapped[str] = mapped_column(String(16), nullable=False)
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    public_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(nullable=True)
    uploaded_by: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)

    annotation = relationship("Annotation", back_populates="attachments")

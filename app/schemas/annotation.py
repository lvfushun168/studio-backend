from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import CamelCaseORMModel


class AnnotationAttachmentRead(CamelCaseORMModel):
    id: int
    annotation_id: int
    filename: str
    media_type: str
    storage_path: str
    public_url: str | None
    size_bytes: int | None


class AnnotationCreate(BaseModel):
    project_id: int
    target_asset_id: int
    target_version: int | None = None
    frame_number: int | None = None
    timestamp_seconds: float | None = None
    canvas_json: dict | None = None
    summary: str | None = None


class AnnotationRead(CamelCaseORMModel):
    id: int
    project_id: int
    target_asset_id: int
    target_version: int | None
    author_id: int
    author_role: str
    frame_number: int | None
    timestamp_seconds: float | None
    canvas_json: dict | None
    overlay_path: str | None
    overlay_url: str | None
    merged_path: str | None
    merged_url: str | None
    summary: str | None
    attachments: list[AnnotationAttachmentRead] = []

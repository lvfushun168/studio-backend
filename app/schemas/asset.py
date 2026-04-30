from datetime import datetime

from pydantic import BaseModel, Field, computed_field

from app.schemas.common import CamelCaseORMModel


class AssetAttachmentRead(CamelCaseORMModel):
    id: int
    asset_id: int
    filename: str
    media_type: str
    storage_path: str
    public_url: str | None
    size_bytes: int | None


class AssetCreate(BaseModel):
    project_id: int
    scene_group_id: int | None = None
    scene_id: int | None = None
    stage_key: str
    asset_type: str = "original"
    media_type: str = "image"
    is_global: bool = False
    original_name: str
    note: str | None = None
    metadata_json: dict | None = None


class AssetRead(CamelCaseORMModel):
    id: int
    project_id: int
    scene_group_id: int | None
    scene_id: int | None
    stage_key: str = Field(serialization_alias="type")
    asset_type: str
    media_type: str
    bank_material_id: int | None
    bank_reference_id: int | None
    is_global: bool
    filename: str
    original_name: str
    extension: str | None
    storage_path: str
    public_url: str | None = Field(serialization_alias="url")
    thumbnail_path: str | None
    thumbnail_url: str | None
    version: int
    note: str | None
    metadata_json: dict | None
    uploaded_by: int = Field(serialization_alias="userId")
    attachments: list[AssetAttachmentRead] = []


class AssetUpdate(BaseModel):
    note: str | None = None
    is_global: bool | None = None

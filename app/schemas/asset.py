from datetime import datetime

from pydantic import BaseModel, Field, computed_field

from app.schemas.common import CamelCaseModel, CamelCaseORMModel


class AssetAttachmentRead(CamelCaseORMModel):
    id: int
    asset_id: int
    filename: str
    media_type: str
    storage_path: str
    public_url: str | None
    size_bytes: int | None
    metadata_json: dict | None = None
    created_at: datetime
    updated_at: datetime


class AssetCreate(CamelCaseModel):
    project_id: int
    scene_group_id: int | None = None
    scene_id: int | None = None
    folder_id: int | None = None
    stage_key: str
    asset_type: str = "original"
    media_type: str = "image"
    is_global: bool = False
    original_name: str
    note: str | None = None
    metadata_json: dict | None = None
    scene_work_step_id: int | None = None
    asset_usage: str = "stage_asset"


class AssetRead(CamelCaseORMModel):
    id: int
    project_id: int
    scene_group_id: int | None
    scene_id: int | None
    folder_id: int | None
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
    scene_work_step_id: int | None
    asset_usage: str
    lifecycle_status: str
    is_invalid: bool
    invalid_reason: str | None
    invalidated_by: int | None
    invalidated_at: datetime | None
    attachments: list[AssetAttachmentRead] = []
    created_at: datetime
    updated_at: datetime


class AssetUpdate(BaseModel):
    note: str | None = None
    is_global: bool | None = None
    folder_id: int | None = None
    metadata_json: dict | None = None

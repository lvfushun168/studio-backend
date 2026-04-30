from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import CamelCaseORMModel


class BankMaterialCreate(BaseModel):
    project_id: int
    source_asset_id: int | None = None
    source_scene_id: int | None = None
    source_stage_key: str | None = None
    name: str = Field(min_length=1, max_length=255)
    character_name: str | None = None
    part_name: str | None = None
    pose: str | None = None
    angle: str | None = None


class BankMaterialRead(CamelCaseORMModel):
    id: int
    project_id: int
    source_asset_id: int | None
    source_scene_id: int | None
    source_stage_key: str | None
    name: str
    character_name: str | None
    part_name: str | None
    pose: str | None
    angle: str | None
    current_asset_id: int | None
    current_version: int | None
    ref_count: int
    status: str
    metadata_json: dict | None
    created_by: int


class BankReferenceCreate(BaseModel):
    bank_material_id: int
    project_id: int
    scene_id: int
    stage_key: str
    version: int | None = None


class BankReferenceRead(CamelCaseORMModel):
    id: int
    bank_material_id: int
    project_id: int
    scene_id: int
    stage_key: str
    version: int | None
    status: str
    detached_asset_id: int | None
    created_by: int | None

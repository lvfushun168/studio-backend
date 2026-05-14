from pydantic import BaseModel

from app.schemas.common import CamelCaseORMModel


class AssetFolderCreate(BaseModel):
    project_id: int
    name: str
    parent_id: int | None = None


class AssetFolderUpdate(BaseModel):
    name: str | None = None
    parent_id: int | None = None


class AssetFolderRead(CamelCaseORMModel):
    id: int
    project_id: int
    parent_id: int | None
    name: str
    created_by: int

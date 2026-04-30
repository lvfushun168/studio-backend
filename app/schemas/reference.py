from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import CamelCaseORMModel


class ReferenceCreate(BaseModel):
    project_id: int
    source_type: str
    source_id: int
    target_type: str
    target_id: int
    relation_type: str | None = "mention"


class ReferenceRead(CamelCaseORMModel):
    id: int
    project_id: int
    source_type: str
    source_id: int
    target_type: str
    target_id: int
    relation_type: str | None
    created_by: int
    created_at: datetime

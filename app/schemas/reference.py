from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class ReferenceCreate(BaseModel):
    project_id: int
    source_type: str
    source_id: int
    target_type: str
    target_id: int
    relation_type: str = "mention"


class ReferenceRead(ORMModel):
    id: int
    project_id: int
    source_type: str
    source_id: int
    target_type: str
    target_id: int
    relation_type: str
    created_by: int
    created_at: datetime

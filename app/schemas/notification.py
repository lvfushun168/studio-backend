from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class NotificationRead(ORMModel):
    id: int
    project_id: int | None
    user_id: int
    type: str
    title: str
    content: str
    status: str
    payload_json: dict | None
    created_at: datetime
    read_at: datetime | None


class NotificationBatchRead(BaseModel):
    ids: list[int]

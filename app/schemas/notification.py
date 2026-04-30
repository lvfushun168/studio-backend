from datetime import datetime

from pydantic import BaseModel, Field, computed_field

from app.schemas.common import CamelCaseORMModel


class NotificationRead(CamelCaseORMModel):
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

    @computed_field
    @property
    def read(self) -> bool:
        return self.status == "read"

    @computed_field
    @property
    def message(self) -> str:
        return self.content or self.title or ""

    @computed_field
    @property
    def scene_id(self) -> int | None:
        return self.payload_json.get("scene_id") if self.payload_json else None

    @computed_field
    @property
    def stage(self) -> str | None:
        return self.payload_json.get("stage") if self.payload_json else None


class NotificationBatchRead(BaseModel):
    ids: list[int]

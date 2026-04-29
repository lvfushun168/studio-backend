from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import TimestampedRead


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    project_type: str = "series"
    status: str = "active"


class ProjectRead(TimestampedRead):
    id: int
    name: str
    description: str | None
    project_type: str
    status: str
    deadline_at: datetime | None
    created_by: int | None

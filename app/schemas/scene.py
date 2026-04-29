from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import TimestampedRead


class StageProgressRead(TimestampedRead):
    id: int
    project_id: int
    scene_id: int
    stage_key: str
    status: str
    reviewer_id: int | None
    reviewed_at: datetime | None
    comment: str | None
    started_at: datetime | None
    submitted_at: datetime | None
    approved_at: datetime | None
    rejected_at: datetime | None


class SceneCreate(BaseModel):
    project_id: int
    scene_group_id: int
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    level: str = "B"
    stage_template: str
    pipeline: str
    frame_count: int = 1
    duration_seconds: float | None = None
    sort_order: int = 0
    created_by: int | None = None


class SceneRead(TimestampedRead):
    id: int
    project_id: int
    scene_group_id: int
    base_scene_id: int | None
    name: str
    description: str | None
    level: str
    stage_template: str
    pipeline: str
    frame_count: int
    duration_seconds: float | None
    sort_order: int
    created_by: int | None
    stage_progresses: list[StageProgressRead] = []

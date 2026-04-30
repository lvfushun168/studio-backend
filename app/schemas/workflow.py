from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import ORMModel


class ReviewRecordRead(ORMModel):
    id: int
    project_id: int
    scene_id: int
    stage_progress_id: int
    stage_key: str
    action: str
    from_status: str | None
    to_status: str
    operator_id: int
    comment: str | None
    extra_json: dict | None
    created_at: datetime


class SubmitRequest(BaseModel):
    stage_key: str
    user_id: int


class ApproveRequest(BaseModel):
    stage_key: str
    user_id: int
    comment: str | None = None


class RejectRequest(BaseModel):
    stage_key: str
    user_id: int
    comment: str | None = None

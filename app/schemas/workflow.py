from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelCaseModel, CamelCaseORMModel


class ReviewRecordRead(CamelCaseORMModel):
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


class SubmitRequest(CamelCaseModel):
    stage_key: str


class ApproveRequest(CamelCaseModel):
    stage_key: str
    comment: str | None = None
    reason_category: str | None = None


class RejectRequest(CamelCaseModel):
    stage_key: str
    comment: str | None = None
    reason_category: str | None = None
    work_step_ids: list[int] = Field(default_factory=list)
    reject_all_submitted_steps: bool = False


class ResubmitRequest(CamelCaseModel):
    stage_key: str

from datetime import datetime

from typing import Literal

from pydantic import BaseModel, Field, computed_field, model_validator

from app.schemas.common import CamelCaseModel, CamelCaseORMModel
from app.schemas.work_step import WorkStepTemplateItemWrite


class StageProgressRead(CamelCaseORMModel):
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
    assignee_id: int | None
    due_at: datetime | None
    priority: str
    blocked_reason: str | None
    production_note: str | None


class SceneAssignmentRead(CamelCaseORMModel):
    id: int
    scene_id: int
    user_id: int
    stage_key: str | None
    assigned_at: datetime


class SceneWorkStepPlan(CamelCaseModel):
    mode: Literal["template", "manual", "stage_delivery"]
    template_id: int | None = None
    items: list[WorkStepTemplateItemWrite] | None = None

    @model_validator(mode="after")
    def validate_plan(self):
        if self.mode == "template" and self.template_id is None:
            raise ValueError("templateId is required when mode is template")
        if self.mode == "manual" and not self.items:
            raise ValueError("items are required when mode is manual")
        return self


class SceneCreate(CamelCaseModel):
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
    base_scene_id: int | None = None
    copy_work_steps_from_scene_id: int | None = None
    work_step_plans: dict[str, SceneWorkStepPlan] | None = None
    created_by: int | None = None


class SceneUpdate(BaseModel):
    scene_group_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    level: str | None = None
    frame_count: int | None = None
    duration_seconds: float | None = None
    sort_order: int | None = None
    base_scene_id: int | None = None


class SceneRead(CamelCaseORMModel):
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
    assignments: list[SceneAssignmentRead] = []

    @computed_field
    @property
    def stage_progress(self) -> dict[str, dict]:
        """Convert stage_progresses array to frontend-expected object format."""
        result: dict[str, dict] = {}
        for sp in self.stage_progresses:
            result[sp.stage_key] = {
                "status": sp.status,
                "reviewerId": sp.reviewer_id,
                "reviewedAt": sp.reviewed_at.isoformat() if sp.reviewed_at else None,
                "comment": sp.comment,
            }
        return result

    @computed_field
    @property
    def assigned_user_ids(self) -> list[int]:
        """Extract unique user IDs from assignments."""
        return list({a.user_id for a in self.assignments})


class SceneSortItem(BaseModel):
    scene_id: int
    sort_order: int


class SceneBatchSortRequest(BaseModel):
    items: list[SceneSortItem]

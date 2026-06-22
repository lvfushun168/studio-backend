from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, field_validator, model_validator

from app.schemas.common import CamelCaseModel, CamelCaseORMModel


Scope = Literal["system", "project"]
WorkStepStatus = Literal["not_ready", "todo", "in_progress", "submitted", "needs_fix", "done", "cancelled"]
Priority = Literal["low", "normal", "high", "urgent"]


class WorkStepTemplateItemWrite(CamelCaseORMModel):
    step_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    sort_order: int = 0
    is_required: bool = True
    allow_parallel: bool = False
    default_duration_hours: Decimal | None = Field(default=None, ge=0)
    default_role: str | None = Field(default=None, max_length=32)
    metadata_json: dict | None = None

    @field_validator("step_key", "name", mode="before")
    @classmethod
    def strip_required_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class WorkStepTemplateItemRead(WorkStepTemplateItemWrite):
    id: int
    template_id: int
    created_at: datetime
    updated_at: datetime


class WorkStepTemplateCreate(CamelCaseModel):
    scope: Scope = "project"
    project_id: int | None = None
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    stage_key: str = Field(min_length=1, max_length=64)
    version: int = Field(default=1, ge=1)
    is_default: bool = False
    is_active: bool = True
    items: list[WorkStepTemplateItemWrite] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_scope_and_items(self):
        if self.scope == "project" and self.project_id is None:
            raise ValueError("projectId is required for project templates")
        if self.scope == "system" and self.project_id is not None:
            raise ValueError("projectId must be empty for system templates")
        keys = [item.step_key for item in self.items]
        if len(keys) != len(set(keys)):
            raise ValueError("item stepKey must be unique within a template")
        return self

    @field_validator("name", "stage_key", mode="before")
    @classmethod
    def strip_required_text(cls, value):
        return value.strip() if isinstance(value, str) else value


class WorkStepTemplateUpdate(CamelCaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    version: int | None = Field(default=None, ge=1)
    is_default: bool | None = None
    is_active: bool | None = None
    items: list[WorkStepTemplateItemWrite] | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_item_keys(self):
        if self.items is not None:
            keys = [item.step_key for item in self.items]
            if len(keys) != len(set(keys)):
                raise ValueError("item stepKey must be unique within a template")
        return self

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, value):
        return value.strip() if isinstance(value, str) else value


class WorkStepTemplateRead(CamelCaseORMModel):
    id: int
    scope: Scope
    project_id: int | None
    name: str
    description: str | None
    stage_key: str
    version: int
    is_default: bool
    is_active: bool
    created_by: int | None
    created_at: datetime
    updated_at: datetime
    items: list[WorkStepTemplateItemRead]


class WorkStepTemplateCopy(CamelCaseModel):
    project_id: int | None = None
    name: str | None = Field(default=None, min_length=1, max_length=128)
    version: int | None = Field(default=None, ge=1)
    is_default: bool = False


class SceneWorkStepCreate(CamelCaseModel):
    step_key: str = Field(min_length=1, max_length=64, pattern=r"^[a-z][a-z0-9_]{0,63}$")
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    sort_order: int = 0
    is_required: bool = True
    allow_parallel: bool = False
    assignee_id: int | None = None
    priority: Priority = "normal"
    due_at: datetime | None = None
    blocked_reason: str | None = Field(default=None, max_length=64)
    note: str | None = None
    metadata_json: dict | None = None


class SceneWorkStepUpdate(CamelCaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    sort_order: int | None = None
    is_required: bool | None = None
    allow_parallel: bool | None = None
    assignee_id: int | None = None
    priority: Priority | None = None
    due_at: datetime | None = None
    blocked_reason: str | None = Field(default=None, max_length=64)
    note: str | None = None
    metadata_json: dict | None = None


class SceneWorkStepRead(CamelCaseORMModel):
    id: int
    project_id: int
    scene_group_id: int
    scene_id: int
    stage_progress_id: int
    stage_key: str
    template_id: int | None
    template_item_id: int | None
    step_key: str
    name: str
    original_name: str | None
    description: str | None
    sort_order: int
    is_required: bool
    allow_parallel: bool
    status: WorkStepStatus
    assignee_id: int | None
    priority: Priority
    due_at: datetime | None
    blocked_reason: str | None
    note: str | None
    started_at: datetime | None
    submitted_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    created_by: int | None
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime


class WorkStepListRead(CamelCaseModel):
    items: list[SceneWorkStepRead]
    total: int


class StepSubmitRequest(CamelCaseModel):
    note: str | None = None
    asset_ids: list[int] = Field(min_length=1)

    @field_validator("asset_ids")
    @classmethod
    def unique_asset_ids(cls, value: list[int]) -> list[int]:
        if len(value) != len(set(value)):
            raise ValueError("assetIds must be unique")
        return value


class StepSubmissionAssetRead(CamelCaseORMModel):
    id: int
    submission_id: int
    asset_id: int
    sort_order: int
    created_at: datetime
    updated_at: datetime


class StepSubmissionRead(CamelCaseORMModel):
    id: int
    project_id: int
    scene_id: int
    scene_work_step_id: int
    stage_progress_id: int
    stage_key: str
    version: int
    status: Literal["submitted", "stage_accepted", "stage_rejected", "withdrawn"]
    submitted_by: int
    note: str | None
    reject_reason: str | None
    reviewed_by: int | None
    reviewed_at: datetime | None
    withdrawn_at: datetime | None
    metadata_json: dict | None
    created_at: datetime
    updated_at: datetime
    assets: list[StepSubmissionAssetRead]

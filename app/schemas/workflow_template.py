from pydantic import Field

from app.schemas.common import CamelCaseModel, CamelCaseORMModel
from app.schemas.system import StageTemplateItem


class WorkflowStageItemWrite(CamelCaseModel):
    key: str | None = Field(default=None, max_length=64)
    label: str = Field(min_length=1, max_length=128)
    needs_review: bool = True
    sub_track: str | None = Field(default=None, max_length=32)


class WorkflowTemplateCreate(CamelCaseModel):
    scope: str = Field(default="project", max_length=16)
    project_id: int | None = None
    name: str = Field(min_length=1, max_length=128)
    description: str | None = None
    based_on_template_key: str | None = Field(default=None, max_length=64)
    is_default: bool = False
    is_active: bool = True
    steps: list[WorkflowStageItemWrite] | None = None


class WorkflowTemplateUpdate(CamelCaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    description: str | None = None
    is_default: bool | None = None
    is_active: bool | None = None
    steps: list[WorkflowStageItemWrite] | None = None


class WorkflowTemplateRead(CamelCaseORMModel):
    id: int
    scope: str
    project_id: int | None
    name: str
    description: str | None
    based_on_template_key: str | None
    is_default: bool
    is_active: bool
    created_by: int | None
    template_key: str
    steps: list[StageTemplateItem]
    scene_count: int = 0
    step_structure_locked: bool = False

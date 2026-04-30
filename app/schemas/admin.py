from datetime import datetime

from pydantic import Field, computed_field

from app.schemas.common import CamelCaseModel, CamelCaseORMModel, TimestampedRead


class AccountCreate(CamelCaseModel):
    name: str = Field(min_length=1, max_length=128)
    email: str = Field(min_length=1, max_length=255)
    provider: str = "gemini"
    status: str = "active"
    remark: str | None = None
    project_ids: list[int] = []
    login_secret: str | None = None
    extra_json: dict | None = None


class AccountUpdate(CamelCaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    email: str | None = Field(default=None, min_length=1, max_length=255)
    provider: str | None = None
    status: str | None = None
    remark: str | None = None
    project_ids: list[int] | None = None
    login_secret: str | None = None
    extra_json: dict | None = None


class AccountVerifyRequest(CamelCaseModel):
    status: str | None = None
    remark: str | None = None


class AccountSyncRequest(CamelCaseModel):
    accounts: list[AccountCreate] = []


class AccountProjectMembershipRead(CamelCaseORMModel):
    project_id: int


class AccountRead(TimestampedRead):
    id: int
    name: str
    email: str
    provider: str
    status: str
    last_check_at: datetime | None
    last_used_at: datetime | None
    success_count: int
    fail_count: int
    remark: str | None
    extra_json: dict | None
    project_memberships: list[AccountProjectMembershipRead] = Field(default_factory=list)

    @computed_field
    @property
    def project_ids(self) -> list[int]:
        return [item.project_id for item in self.project_memberships]


class PromptCreate(CamelCaseModel):
    name: str = Field(min_length=1, max_length=255)
    content: str = Field(min_length=1)
    aspect_ratio: str = "auto"
    resolution: str = "2k"
    scope: str = "global"
    project_id: int | None = None
    user_id: int | None = None
    is_active: bool = True


class PromptUpdate(CamelCaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    content: str | None = None
    aspect_ratio: str | None = None
    resolution: str | None = None
    scope: str | None = None
    project_id: int | None = None
    user_id: int | None = None
    is_active: bool | None = None


class PromptRead(TimestampedRead):
    id: int
    name: str
    content: str
    aspect_ratio: str
    resolution: str
    scope: str
    project_id: int | None
    user_id: int | None
    last_used_at: datetime | None
    use_count: int
    is_active: bool


class ImageGroupImageCreate(CamelCaseModel):
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1)
    thumbnail_url: str | None = None
    sort_order: int = 0
    metadata_json: dict | None = None


class ImageGroupImageUpdate(CamelCaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    url: str | None = None
    thumbnail_url: str | None = None
    sort_order: int | None = None
    metadata_json: dict | None = None


class ImageGroupCreate(CamelCaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    project_id: int | None = None
    user_id: int | None = None
    is_shared: bool = False
    images: list[ImageGroupImageCreate] = []


class ImageGroupUpdate(CamelCaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    project_id: int | None = None
    user_id: int | None = None
    is_shared: bool | None = None


class ImageGroupImageRead(TimestampedRead):
    id: int
    name: str
    url: str
    thumbnail_url: str | None
    sort_order: int
    metadata_json: dict | None


class ImageGroupRead(TimestampedRead):
    id: int
    name: str
    description: str | None
    project_id: int | None
    user_id: int | None
    is_shared: bool
    images: list[ImageGroupImageRead] = []


class GenerationTemplateSnapshot(CamelCaseORMModel):
    image_group_id: int | None = None
    prompt: str = ""
    aspect_ratio: str = "auto"
    resolution: str = "2k"
    count: int = 4


class GenerationTemplateCreate(CamelCaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    snapshot: dict
    user_id: int | None = None
    project_id: int | None = None


class GenerationTemplateUpdate(CamelCaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    snapshot: dict | None = None
    user_id: int | None = None
    project_id: int | None = None


class GenerationTemplateRead(TimestampedRead):
    id: int
    name: str
    description: str | None
    snapshot_json: dict = Field(serialization_alias="snapshot")
    user_id: int | None
    project_id: int | None


class GenerationTaskCreate(CamelCaseModel):
    user_id: int | None = None
    project_id: int
    scene_id: int | None = None
    stage_key: str | None = Field(default=None, validation_alias="stage", serialization_alias="stage")
    account_id: int | None = None
    image_group_id: int | None = None
    prompt_id: int | None = None
    prompt_content: str = ""
    aspect_ratio: str = "auto"
    resolution: str = "2k"
    status: str = "pending"
    requested_count: int = 4
    result_count: int = 0
    completed_at: datetime | None = None
    fail_reason: str | None = None
    metadata_json: dict | None = None


class GenerationTaskUpdate(CamelCaseModel):
    account_id: int | None = None
    prompt_id: int | None = None
    prompt_content: str | None = None
    aspect_ratio: str | None = None
    resolution: str | None = None
    status: str | None = None
    requested_count: int | None = None
    result_count: int | None = None
    completed_at: datetime | None = None
    fail_reason: str | None = None
    metadata_json: dict | None = None


class GenerationTaskRead(TimestampedRead):
    id: int
    user_id: int
    project_id: int
    scene_id: int | None
    stage_key: str | None = Field(serialization_alias="stage")
    account_id: int | None
    image_group_id: int | None
    prompt_id: int | None
    prompt_content: str
    aspect_ratio: str
    resolution: str
    status: str
    requested_count: int
    result_count: int
    completed_at: datetime | None
    fail_reason: str | None
    metadata_json: dict | None


class GenerationResultCreate(CamelCaseModel):
    task_id: int
    user_id: int | None = None
    project_id: int
    scene_id: int | None = None
    stage_key: str | None = Field(default=None, validation_alias="stage", serialization_alias="stage")
    image_group_id: int | None = None
    prompt_id: int | None = None
    name: str = Field(min_length=1, max_length=255)
    url: str = Field(min_length=1)
    thumbnail_url: str | None = None
    status: str = "pending"
    review_comment: str | None = None
    reviewed_by: int | None = None
    reviewed_at: datetime | None = None
    metadata_json: dict | None = None


class GenerationResultUpdate(CamelCaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    url: str | None = None
    thumbnail_url: str | None = None
    status: str | None = None
    review_comment: str | None = None
    reviewed_by: int | None = None
    reviewed_at: datetime | None = None
    metadata_json: dict | None = None


class ReviewRequest(CamelCaseModel):
    status: str
    comment: str | None = None


class SubmitResultRequest(CamelCaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)


class GenerationResultRead(TimestampedRead):
    id: int
    task_id: int
    user_id: int
    project_id: int
    scene_id: int | None
    stage_key: str | None = Field(serialization_alias="stage")
    image_group_id: int | None
    prompt_id: int | None
    name: str
    url: str
    thumbnail_url: str | None
    status: str
    review_comment: str | None
    reviewed_by: int | None
    reviewed_at: datetime | None
    metadata_json: dict | None


class DashboardStatusCount(CamelCaseORMModel):
    key: str
    count: int


class DashboardRead(CamelCaseORMModel):
    account_count: int
    user_count: int
    project_count: int
    task_count: int
    result_count: int
    pending_review_count: int
    account_statuses: list[DashboardStatusCount]
    recent_tasks: list[GenerationTaskRead]


class AuditLogRead(TimestampedRead):
    id: int
    user_id: int | None
    project_id: int | None
    action: str
    target_type: str
    target_id: int | None
    summary: str | None
    payload_json: dict | None

from datetime import datetime

from app.schemas.common import CamelCaseModel


class ActivityEventRead(CamelCaseModel):
    id: str
    source: str
    occurred_at: datetime
    action: str
    action_label: str
    summary: str
    actor_id: int | None = None
    actor_name: str | None = None
    actor_role: str | None = None
    project_id: int | None = None
    scene_id: int | None = None
    asset_id: int | None = None
    stage_key: str | None = None
    target_type: str | None = None
    target_id: int | None = None
    target_label: str | None = None
    from_status: str | None = None
    to_status: str | None = None
    reason_category: str | None = None
    details: dict | None = None

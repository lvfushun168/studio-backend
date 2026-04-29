from pydantic import BaseModel


class HealthRead(BaseModel):
    status: str
    app: str
    env: str


class StageTemplateItem(BaseModel):
    key: str
    label: str
    needs_review: bool
    sub_track: str | None = None


class BootstrapRead(BaseModel):
    app_name: str
    stage_templates: dict[str, list[StageTemplateItem]]

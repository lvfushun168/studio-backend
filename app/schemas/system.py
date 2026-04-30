from pydantic import BaseModel


class HealthDependencyRead(BaseModel):
    ok: bool
    detail: str


class HealthRead(BaseModel):
    status: str
    app: str
    env: str
    database: HealthDependencyRead
    storage: HealthDependencyRead


class StageTemplateItem(BaseModel):
    key: str
    label: str
    needs_review: bool
    sub_track: str | None = None


class BootstrapRead(BaseModel):
    app_name: str
    stage_templates: dict[str, list[StageTemplateItem]]

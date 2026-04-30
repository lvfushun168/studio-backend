from pydantic import BaseModel, Field

from app.schemas.common import CamelCaseORMModel


class SceneGroupCreate(BaseModel):
    project_id: int
    episode_id: int | None = None
    name: str = Field(min_length=1, max_length=255)
    sort_order: int = 0


class SceneGroupRead(CamelCaseORMModel):
    id: int
    project_id: int
    episode_id: int | None
    name: str
    sort_order: int

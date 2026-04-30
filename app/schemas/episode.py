from pydantic import BaseModel, Field

from app.schemas.common import TimestampedRead


class EpisodeCreate(BaseModel):
    project_id: int
    episode_number: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=255)


class EpisodeRead(TimestampedRead):
    id: int
    project_id: int
    episode_number: int
    name: str

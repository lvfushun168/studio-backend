from datetime import datetime

from pydantic import Field, computed_field

from app.schemas.common import CamelCaseModel, CamelCaseORMModel


class ProjectCreate(CamelCaseModel):
    name: str = Field(min_length=1, max_length=255)
    description: str | None = None
    project_type: str = "series"
    status: str = "active"
    deadline_at: datetime | None = None
    member_ids: list[int] = []


class ProjectUpdate(CamelCaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    description: str | None = None
    project_type: str | None = None
    status: str | None = None
    deadline_at: datetime | None = None
    member_ids: list[int] | None = None


class ProjectMemberRead(CamelCaseORMModel):
    user_id: int
    role_in_project: str | None


class ProjectMemberWrite(CamelCaseModel):
    user_id: int
    role_in_project: str | None = None


class ProjectRead(CamelCaseORMModel):
    id: int
    name: str
    description: str | None
    cover_path: str | None = None
    cover_url: str | None = None
    project_type: str = Field(serialization_alias="type")
    status: str
    deadline_at: datetime | None
    created_by: int | None
    members: list[ProjectMemberRead] = []

    @computed_field
    @property
    def member_ids(self) -> list[int]:
        return [m.user_id for m in self.members]

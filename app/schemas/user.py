from datetime import datetime

from datetime import datetime

from pydantic import Field, computed_field

from app.schemas.common import CamelCaseModel, CamelCaseORMModel, TimestampedRead


class UserCreate(CamelCaseModel):
    username: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    email: str | None = None
    role: str = "artist"
    password: str | None = None
    is_active: bool = True
    project_ids: list[int] = []


class UserUpdate(CamelCaseModel):
    username: str | None = Field(default=None, min_length=1, max_length=64)
    display_name: str | None = Field(default=None, min_length=1, max_length=128)
    email: str | None = None
    role: str | None = None
    password: str | None = None
    is_active: bool | None = None
    project_ids: list[int] | None = None


class UserMembershipRead(CamelCaseORMModel):
    project_id: int
    role_in_project: str | None = None


class UserRead(TimestampedRead):
    id: int
    username: str
    display_name: str
    email: str | None
    role: str
    is_active: bool
    api_key: str | None = None
    last_login_at: datetime | None = None
    memberships: list[UserMembershipRead] = []

    @computed_field
    @property
    def project_ids(self) -> list[int]:
        return [item.project_id for item in self.memberships]

    @computed_field
    @property
    def status(self) -> str:
        return "active" if self.is_active else "inactive"


class UserMeRead(UserRead):
    api_key: str | None = None


class UserLogin(CamelCaseModel):
    username: str
    password: str = ""

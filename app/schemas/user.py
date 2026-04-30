from datetime import datetime

from pydantic import BaseModel, Field

from app.schemas.common import TimestampedRead


class UserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=64)
    display_name: str = Field(min_length=1, max_length=128)
    email: str | None = None
    role: str = "artist"
    password: str | None = None
    is_active: bool = True


class UserRead(TimestampedRead):
    id: int
    username: str
    display_name: str
    email: str | None
    role: str
    is_active: bool


class UserMeRead(UserRead):
    api_key: str | None = None


class UserLogin(BaseModel):
    username: str
    password: str = ""

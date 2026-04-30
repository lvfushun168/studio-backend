from datetime import datetime

from pydantic import Field

from app.schemas.common import CamelCaseModel, CamelCaseORMModel
from app.schemas.user import UserRead


class LoginRequest(CamelCaseModel):
    username: str = Field(min_length=1, max_length=64)
    password: str = Field(min_length=1, max_length=255)


class LoginResponse(CamelCaseORMModel):
    token: str
    expires_at: datetime
    user: UserRead


class ChangePasswordRequest(CamelCaseModel):
    current_password: str = Field(min_length=1, max_length=255)
    new_password: str = Field(min_length=6, max_length=255)


class ResetPasswordRequest(CamelCaseModel):
    new_password: str = Field(min_length=6, max_length=255)


class LogoutResponse(CamelCaseORMModel):
    success: bool

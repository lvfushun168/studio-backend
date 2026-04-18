from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.account import AccountStatus


class AccountCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    email: str | None = None
    account_id: str | None = None
    secure_1psid: str = Field(min_length=10)
    secure_1psidts: str | None = None
    model_hint: str | None = None
    notes: str | None = None


class AccountRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    name: str
    email: str | None
    account_id: str | None
    status: AccountStatus
    model_hint: str | None
    last_verified_at: datetime | None
    last_used_at: datetime | None
    cooldown_until: datetime | None
    fail_count: int
    success_count: int
    notes: str | None
    created_at: datetime
    updated_at: datetime


class AccountListItem(AccountRead):
    pass


class AccountVerifyResult(BaseModel):
    ok: bool
    email: str | None = None
    account_id: str | None = None
    status: str
    psid_hash: str


class BrowserImportResult(BaseModel):
    imported: int
    accounts: list[AccountRead]

from datetime import datetime

from pydantic import BaseModel

from app.schemas.common import CamelCaseORMModel


class AsyncJobCreate(BaseModel):
    project_id: int | None = None
    job_type: str
    priority: int = 100
    payload_json: dict
    max_retries: int = 3


class AsyncJobRetry(BaseModel):
    reset_error: bool = True


class AsyncJobRead(CamelCaseORMModel):
    id: int
    project_id: int | None
    job_type: str
    status: str
    priority: int
    payload_json: dict
    result_json: dict | None
    error_message: str | None
    retry_count: int
    max_retries: int
    scheduled_at: datetime | None
    started_at: datetime | None
    finished_at: datetime | None
    created_by: int | None
    created_at: datetime
    updated_at: datetime


class ExportJobCreate(BaseModel):
    priority: int = 50

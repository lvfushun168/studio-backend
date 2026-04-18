from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.task import TaskStatus


class TaskCreate(BaseModel):
    prompt: str = Field(min_length=1)
    mode: str = "pro"
    model_name: str | None = None
    image_count: int = Field(default=1, ge=1, le=4)
    input_paths: list[str] = Field(default_factory=list)


class TaskInputRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_path: str
    sort_order: int


class TaskOutputRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    file_path: str
    created_at: datetime


class TaskRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    task_no: str
    account_id: int | None
    status: TaskStatus
    mode: str
    model_name: str | None
    prompt: str
    error_message: str | None
    image_count: int
    created_at: datetime
    started_at: datetime | None
    finished_at: datetime | None
    inputs: list[TaskInputRead] = Field(default_factory=list)
    outputs: list[TaskOutputRead] = Field(default_factory=list)

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.schemas.task import TaskCreate, TaskRead
from app.services.task_service import TaskService


router = APIRouter()


@router.get("", response_model=list[TaskRead])
def list_tasks(db: Session = Depends(get_db)) -> list[TaskRead]:
    return TaskService(db).list_tasks()


@router.get("/{task_id}", response_model=TaskRead)
def get_task(task_id: int, db: Session = Depends(get_db)) -> TaskRead:
    task = TaskService(db).get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Task not found")
    return task


@router.post("", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
def create_task(payload: TaskCreate, db: Session = Depends(get_db)) -> TaskRead:
    try:
        return TaskService(db).create_task(payload)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/upload", response_model=TaskRead, status_code=status.HTTP_201_CREATED)
async def create_task_with_uploads(
    prompt: str = Form(...),
    mode: str = Form("pro"),
    model_name: str | None = Form(None),
    image_count: int = Form(1),
    files: list[UploadFile] = File(default=[]),
    db: Session = Depends(get_db),
) -> TaskRead:
    try:
        uploaded_files: list[tuple[str, bytes]] = []
        for item in files:
            uploaded_files.append((item.filename or "upload.bin", await item.read()))
        return TaskService(db).create_task_with_uploaded_files(
            prompt=prompt,
            mode=mode,
            model_name=model_name,
            image_count=image_count,
            uploaded_files=uploaded_files,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

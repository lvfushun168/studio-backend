from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import DIRECTOR_ROLES, CurrentUser, require_project_access, require_role
from app.core.database import get_db
from app.models.admin import GenerationResult, GenerationTask, PromptTemplate
from app.schemas.admin import (
    GenerationResultCreate,
    GenerationResultRead,
    GenerationResultUpdate,
    GenerationTaskCreate,
    GenerationTaskRead,
    GenerationTaskUpdate,
    ReviewRequest,
    SubmitResultRequest,
)
from app.services.audit_service import record_audit

router = APIRouter()


def _ensure_task_access(task: GenerationTask, current_user: CurrentUser, db: Session) -> None:
    require_project_access(task.project_id, current_user, db)
    if current_user.role != "admin" and task.user_id != current_user.id and current_user.role not in {"director", "producer"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Task access denied")


def _ensure_result_access(result: GenerationResult, current_user: CurrentUser, db: Session) -> None:
    require_project_access(result.project_id, current_user, db)
    if current_user.role != "admin" and result.user_id != current_user.id and current_user.role not in {"director", "producer"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Result access denied")


def _sync_task_counts(db: Session, task_id: int) -> None:
    count = db.scalar(select(func.count(GenerationResult.id)).where(GenerationResult.task_id == task_id)) or 0
    task = db.get(GenerationTask, task_id)
    if task:
        task.result_count = count
        if task.status == "pending" and count > 0:
            task.status = "success"
            task.completed_at = datetime.now(timezone.utc)


@router.get("/tasks", response_model=list[GenerationTaskRead])
def list_generation_tasks(
    project_id: int | None = None,
    user_id: int | None = None,
    status_filter: str | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[GenerationTask]:
    stmt = select(GenerationTask).order_by(GenerationTask.id.desc())
    if project_id is not None:
        require_project_access(project_id, current_user, db)
        stmt = stmt.where(GenerationTask.project_id == project_id)
    elif current_user.role != "admin":
        accessible_ids: list[int] = []
        from app.core.auth import get_accessible_project_ids
        accessible_ids = get_accessible_project_ids(current_user, db)
        stmt = stmt.where(GenerationTask.project_id.in_(accessible_ids))
    if user_id is not None:
        stmt = stmt.where(GenerationTask.user_id == user_id)
    if status_filter is not None:
        stmt = stmt.where(GenerationTask.status == status_filter)
    return list(db.scalars(stmt).all())


@router.post("/tasks", response_model=GenerationTaskRead, status_code=status.HTTP_201_CREATED)
def create_generation_task(payload: GenerationTaskCreate, current_user: CurrentUser, db: Session = Depends(get_db)) -> GenerationTask:
    require_project_access(payload.project_id, current_user, db)
    owner_id = payload.user_id or current_user.id
    task = GenerationTask(
        user_id=owner_id,
        project_id=payload.project_id,
        scene_id=payload.scene_id,
        stage_key=payload.stage_key,
        account_id=payload.account_id,
        image_group_id=payload.image_group_id,
        prompt_id=payload.prompt_id,
        prompt_content=payload.prompt_content,
        aspect_ratio=payload.aspect_ratio,
        resolution=payload.resolution,
        status=payload.status,
        requested_count=payload.requested_count,
        result_count=payload.result_count,
        completed_at=payload.completed_at,
        fail_reason=payload.fail_reason,
        metadata_json=payload.metadata_json,
    )
    db.add(task)
    if payload.prompt_id:
        prompt = db.get(PromptTemplate, payload.prompt_id)
        if prompt:
            prompt.use_count += 1
            prompt.last_used_at = datetime.now(timezone.utc)
    record_audit(db, user_id=current_user.id, action="generation.task_create", target_type="generation_task", summary=f"Created generation task for project {payload.project_id}", project_id=payload.project_id)
    db.commit()
    return task


@router.get("/tasks/{task_id}", response_model=GenerationTaskRead)
def get_generation_task(task_id: int, current_user: CurrentUser, db: Session = Depends(get_db)) -> GenerationTask:
    task = db.get(GenerationTask, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    _ensure_task_access(task, current_user, db)
    return task


@router.put("/tasks/{task_id}", response_model=GenerationTaskRead)
def update_generation_task(task_id: int, payload: GenerationTaskUpdate, current_user: CurrentUser, db: Session = Depends(get_db)) -> GenerationTask:
    task = db.get(GenerationTask, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    _ensure_task_access(task, current_user, db)
    for field in ["account_id", "prompt_id", "prompt_content", "aspect_ratio", "resolution", "status", "requested_count", "result_count", "completed_at", "fail_reason", "metadata_json"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(task, field, value)
    record_audit(db, user_id=current_user.id, action="generation.task_update", target_type="generation_task", target_id=task.id, project_id=task.project_id, summary=f"Updated task {task.id}")
    db.commit()
    return task


@router.post("/tasks/{task_id}/retry", response_model=GenerationTaskRead)
def retry_generation_task(task_id: int, current_user: CurrentUser, db: Session = Depends(get_db)) -> GenerationTask:
    task = db.get(GenerationTask, task_id)
    if not task:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Task not found")
    _ensure_task_access(task, current_user, db)
    task.status = "pending"
    task.fail_reason = None
    task.completed_at = None
    record_audit(db, user_id=current_user.id, action="generation.task_retry", target_type="generation_task", target_id=task.id, project_id=task.project_id, summary=f"Retried task {task.id}")
    db.commit()
    return task


@router.get("/results", response_model=list[GenerationResultRead])
def list_generation_results(
    project_id: int | None = None,
    scene_id: int | None = None,
    task_id: int | None = None,
    status_filter: str | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[GenerationResult]:
    stmt = select(GenerationResult).order_by(GenerationResult.id.desc())
    if project_id is not None:
        require_project_access(project_id, current_user, db)
        stmt = stmt.where(GenerationResult.project_id == project_id)
    elif current_user.role != "admin":
        from app.core.auth import get_accessible_project_ids
        stmt = stmt.where(GenerationResult.project_id.in_(get_accessible_project_ids(current_user, db)))
    if scene_id is not None:
        stmt = stmt.where(GenerationResult.scene_id == scene_id)
    if task_id is not None:
        stmt = stmt.where(GenerationResult.task_id == task_id)
    if status_filter is not None:
        stmt = stmt.where(GenerationResult.status == status_filter)
    return list(db.scalars(stmt).all())


@router.post("/results", response_model=GenerationResultRead, status_code=status.HTTP_201_CREATED)
def create_generation_result(payload: GenerationResultCreate, current_user: CurrentUser, db: Session = Depends(get_db)) -> GenerationResult:
    require_project_access(payload.project_id, current_user, db)
    result = GenerationResult(
        task_id=payload.task_id,
        user_id=payload.user_id or current_user.id,
        project_id=payload.project_id,
        scene_id=payload.scene_id,
        stage_key=payload.stage_key,
        image_group_id=payload.image_group_id,
        prompt_id=payload.prompt_id,
        name=payload.name,
        url=payload.url,
        thumbnail_url=payload.thumbnail_url or payload.url,
        status=payload.status,
        review_comment=payload.review_comment,
        reviewed_by=payload.reviewed_by,
        reviewed_at=payload.reviewed_at,
        metadata_json=payload.metadata_json,
    )
    db.add(result)
    db.flush()
    _sync_task_counts(db, payload.task_id)
    record_audit(db, user_id=current_user.id, action="generation.result_create", target_type="generation_result", target_id=result.id, project_id=result.project_id, summary=f"Created result {result.name}")
    db.commit()
    return result


@router.get("/results/submitted", response_model=list[GenerationResultRead])
def list_submitted_results(
    project_id: int | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[GenerationResult]:
    stmt = select(GenerationResult).where(GenerationResult.status == "submitted").order_by(GenerationResult.id.desc())
    if project_id is not None:
        require_project_access(project_id, current_user, db)
        stmt = stmt.where(GenerationResult.project_id == project_id)
    elif current_user.role != "admin":
        from app.core.auth import get_accessible_project_ids
        stmt = stmt.where(GenerationResult.project_id.in_(get_accessible_project_ids(current_user, db)))
    return list(db.scalars(stmt).all())


@router.get("/results/approved", response_model=list[GenerationResultRead])
def list_approved_results(
    scene_id: int | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[GenerationResult]:
    stmt = select(GenerationResult).where(GenerationResult.status == "approved").order_by(GenerationResult.id.desc())
    if scene_id is not None:
        stmt = stmt.where(GenerationResult.scene_id == scene_id)
    if current_user.role != "admin":
        from app.core.auth import get_accessible_project_ids
        stmt = stmt.where(GenerationResult.project_id.in_(get_accessible_project_ids(current_user, db)))
    return list(db.scalars(stmt).all())


@router.get("/results/{result_id}", response_model=GenerationResultRead)
def get_generation_result(result_id: int, current_user: CurrentUser, db: Session = Depends(get_db)) -> GenerationResult:
    result = db.get(GenerationResult, result_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found")
    _ensure_result_access(result, current_user, db)
    return result


@router.put("/results/{result_id}", response_model=GenerationResultRead)
def update_generation_result(result_id: int, payload: GenerationResultUpdate, current_user: CurrentUser, db: Session = Depends(get_db)) -> GenerationResult:
    result = db.get(GenerationResult, result_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found")
    _ensure_result_access(result, current_user, db)
    for field in ["name", "url", "thumbnail_url", "status", "review_comment", "reviewed_by", "reviewed_at", "metadata_json"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(result, field, value)
    record_audit(db, user_id=current_user.id, action="generation.result_update", target_type="generation_result", target_id=result.id, project_id=result.project_id, summary=f"Updated result {result.id}")
    db.commit()
    return result


@router.post("/results/{result_id}/submit", response_model=GenerationResultRead)
def submit_generation_result(result_id: int, payload: SubmitResultRequest, current_user: CurrentUser, db: Session = Depends(get_db)) -> GenerationResult:
    result = db.get(GenerationResult, result_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found")
    _ensure_result_access(result, current_user, db)
    if payload.name:
        result.name = payload.name
    result.status = "submitted"
    result.review_comment = None
    result.reviewed_by = None
    result.reviewed_at = None
    db.commit()
    return result


@router.post("/results/{result_id}/review", response_model=GenerationResultRead)
def review_generation_result(result_id: int, payload: ReviewRequest, current_user: CurrentUser, db: Session = Depends(get_db)) -> GenerationResult:
    require_role(DIRECTOR_ROLES)(current_user)
    result = db.get(GenerationResult, result_id)
    if not result:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Result not found")
    require_project_access(result.project_id, current_user, db)
    result.status = payload.status
    result.review_comment = payload.comment
    result.reviewed_by = current_user.id
    result.reviewed_at = datetime.now(timezone.utc)
    record_audit(db, user_id=current_user.id, action="generation.result_review", target_type="generation_result", target_id=result.id, project_id=result.project_id, summary=f"Reviewed result {result.id} as {payload.status}")
    db.commit()
    return result

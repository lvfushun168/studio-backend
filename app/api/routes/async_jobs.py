from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, DIRECTOR_PRODUCER_ROLES, get_accessible_project_ids, require_project_access, require_role
from app.core.database import get_db
from app.models.async_job import AsyncJob
from app.models.project import Project
from app.schemas.async_job import AsyncJobCreate, AsyncJobRead, AsyncJobRetry, ExportJobCreate
from app.services.job_service import enqueue_job, retry_job

router = APIRouter()


@router.get("", response_model=list[AsyncJobRead])
def list_async_jobs(
    project_id: int | None = None,
    status_filter: str | None = None,
    job_type: str | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[AsyncJob]:
    stmt = select(AsyncJob).order_by(AsyncJob.id.desc())
    if project_id is not None:
        require_project_access(project_id, current_user, db)
        stmt = stmt.where(AsyncJob.project_id == project_id)
    elif current_user.role != "admin":
        accessible = get_accessible_project_ids(current_user, db)
        stmt = stmt.where((AsyncJob.project_id.is_(None)) | (AsyncJob.project_id.in_(accessible)))
    if status_filter is not None:
        stmt = stmt.where(AsyncJob.status == status_filter)
    if job_type is not None:
        stmt = stmt.where(AsyncJob.job_type == job_type)
    return list(db.scalars(stmt).all())


@router.post("", response_model=AsyncJobRead, status_code=status.HTTP_201_CREATED)
def create_async_job(
    payload: AsyncJobCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> AsyncJob:
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    if payload.project_id is not None:
        require_project_access(payload.project_id, current_user, db)
    job = enqueue_job(
        db,
        job_type=payload.job_type,
        payload_json=payload.payload_json,
        project_id=payload.project_id,
        created_by=current_user.id,
        priority=payload.priority,
        max_retries=payload.max_retries,
    )
    db.commit()
    db.refresh(job)
    return job


@router.get("/{job_id}", response_model=AsyncJobRead)
def get_async_job(
    job_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> AsyncJob:
    job = db.get(AsyncJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AsyncJob not found")
    if job.project_id is not None:
        require_project_access(job.project_id, current_user, db)
    elif current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Job access denied")
    return job


@router.post("/{job_id}/retry", response_model=AsyncJobRead)
def retry_async_job(
    job_id: int,
    payload: AsyncJobRetry,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> AsyncJob:
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    job = db.get(AsyncJob, job_id)
    if not job:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="AsyncJob not found")
    if job.project_id is not None:
        require_project_access(job.project_id, current_user, db)
    if job.retry_count >= job.max_retries:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Max retries reached")
    if payload.reset_error:
        job.error_message = None
    retry_job(db, job)
    db.commit()
    db.refresh(job)
    return job


@router.post("/projects/{project_id}/export", response_model=AsyncJobRead, status_code=status.HTTP_201_CREATED)
def create_project_export_job(
    project_id: int,
    payload: ExportJobCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> AsyncJob:
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    require_project_access(project_id, current_user, db)
    job = enqueue_job(
        db,
        project_id=project_id,
        job_type="project_export",
        payload_json={"project_id": project_id, "requested_at": datetime.now(timezone.utc).isoformat()},
        created_by=current_user.id,
        priority=payload.priority,
        max_retries=3,
    )
    db.commit()
    db.refresh(job)
    return job

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import ARTIST_ROLES, CurrentUser, DIRECTOR_ROLES, require_project_access, require_role
from app.core.database import get_db
from app.models.scene import Scene, StageProgress
from app.models.workflow import ReviewRecord
from app.schemas.workflow import (
    ApproveRequest,
    RejectRequest,
    ResubmitRequest,
    ReviewRecordRead,
    SubmitRequest,
)
from app.services import workflow_service

router = APIRouter()


@router.post("/scenes/{scene_id}/submit", response_model=list[ReviewRecordRead])
def submit_scene(
    scene_id: int,
    payload: SubmitRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[ReviewRecord]:
    scene = db.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    require_role(ARTIST_ROLES)(current_user)
    require_project_access(scene.project_id, current_user, db)

    record = workflow_service.submit_stage(db, scene, payload.stage_key, current_user.id)
    return [record]


@router.post("/scenes/{scene_id}/approve", response_model=list[ReviewRecordRead])
def approve_scene(
    scene_id: int,
    payload: ApproveRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[ReviewRecord]:
    require_role(DIRECTOR_ROLES)(current_user)
    scene = db.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    require_project_access(scene.project_id, current_user, db)

    records = workflow_service.approve_stage(
        db, scene, payload.stage_key, current_user.id, payload.comment
    )
    return records


@router.post("/scenes/{scene_id}/reject", response_model=list[ReviewRecordRead])
def reject_scene(
    scene_id: int,
    payload: RejectRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[ReviewRecord]:
    require_role(DIRECTOR_ROLES)(current_user)
    scene = db.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    require_project_access(scene.project_id, current_user, db)

    records = workflow_service.reject_stage(
        db, scene, payload.stage_key, current_user.id, payload.comment
    )
    return records


@router.post("/scenes/{scene_id}/resubmit", response_model=ReviewRecordRead)
def resubmit_scene(
    scene_id: int,
    payload: ResubmitRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> ReviewRecord:
    scene = db.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    require_role(ARTIST_ROLES)(current_user)
    require_project_access(scene.project_id, current_user, db)

    record = workflow_service.resubmit_stage(db, scene, payload.stage_key, current_user.id)
    return record


@router.get("/scenes/{scene_id}/records", response_model=list[ReviewRecordRead])
def list_review_records(
    scene_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[ReviewRecord]:
    scene = db.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    require_project_access(scene.project_id, current_user, db)
    stmt = select(ReviewRecord).where(ReviewRecord.scene_id == scene_id).order_by(ReviewRecord.id.desc())
    return list(db.scalars(stmt).all())

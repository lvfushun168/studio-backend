from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.domains.stage_templates import STAGE_TEMPLATES
from app.models.scene import Scene, StageProgress
from app.models.workflow import ReviewRecord
from app.schemas.workflow import ApproveRequest, RejectRequest, ReviewRecordRead, SubmitRequest

router = APIRouter()


def _get_template_keys(stage_template: str) -> list[str]:
    return [item["key"] for item in STAGE_TEMPLATES.get(stage_template, STAGE_TEMPLATES["ai_single_frame"])]


def _is_layout_stage(stage_key: str) -> bool:
    return stage_key in ("layout_character", "layout_background")


def _check_layout_unlock(scene: Scene, db: Session) -> str | None:
    keys = _get_template_keys(scene.stage_template)
    if "layout_character" not in keys or "layout_background" not in keys:
        return None
    progresses = {sp.stage_key: sp for sp in scene.stage_progresses}
    lc = progresses.get("layout_character")
    lb = progresses.get("layout_background")
    if lc and lb and lc.status == "approved" and lb.status == "approved":
        idx = max(keys.index("layout_character"), keys.index("layout_background"))
        if idx + 1 < len(keys):
            return keys[idx + 1]
    return None


@router.post("/scenes/{scene_id}/submit", response_model=list[ReviewRecordRead])
def submit_scene(scene_id: int, payload: SubmitRequest, db: Session = Depends(get_db)) -> list[ReviewRecord]:
    scene = db.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")

    stmt = select(StageProgress).where(StageProgress.scene_id == scene_id, StageProgress.stage_key == payload.stage_key)
    sp = db.scalar(stmt)
    if not sp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="StageProgress not found")

    if sp.status not in ("pending", "in_progress", "rejected"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot submit from current status")

    from_status = sp.status
    sp.status = "reviewing"
    sp.submitted_at = db.scalar(select(StageProgress.created_at))  # placeholder, use func.now() via onupdate

    db.add(sp)
    db.flush()

    record = ReviewRecord(
        project_id=scene.project_id,
        scene_id=scene_id,
        stage_progress_id=sp.id,
        stage_key=payload.stage_key,
        action="submit",
        from_status=from_status,
        to_status="reviewing",
        operator_id=payload.user_id,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return [record]


@router.post("/scenes/{scene_id}/approve", response_model=list[ReviewRecordRead])
def approve_scene(scene_id: int, payload: ApproveRequest, db: Session = Depends(get_db)) -> list[ReviewRecord]:
    scene = db.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")

    stmt = select(StageProgress).where(StageProgress.scene_id == scene_id, StageProgress.stage_key == payload.stage_key)
    sp = db.scalar(stmt)
    if not sp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="StageProgress not found")

    if sp.status != "reviewing":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Stage is not under review")

    from_status = sp.status
    sp.status = "approved"
    sp.reviewer_id = payload.user_id

    records: list[ReviewRecord] = []
    record = ReviewRecord(
        project_id=scene.project_id,
        scene_id=scene_id,
        stage_progress_id=sp.id,
        stage_key=payload.stage_key,
        action="approve",
        from_status=from_status,
        to_status="approved",
        operator_id=payload.user_id,
        comment=payload.comment,
    )
    db.add(record)
    records.append(record)

    # Unlock next stage or layout partner check
    keys = _get_template_keys(scene.stage_template)
    current_idx = keys.index(payload.stage_key)

    if _is_layout_stage(payload.stage_key):
        next_key = _check_layout_unlock(scene, db)
        if next_key:
            next_stmt = select(StageProgress).where(StageProgress.scene_id == scene_id, StageProgress.stage_key == next_key)
            next_sp = db.scalar(next_stmt)
            if next_sp and next_sp.status == "locked":
                next_sp.status = "pending"
    else:
        if current_idx + 1 < len(keys):
            next_key = keys[current_idx + 1]
            next_stmt = select(StageProgress).where(StageProgress.scene_id == scene_id, StageProgress.stage_key == next_key)
            next_sp = db.scalar(next_stmt)
            if next_sp and next_sp.status == "locked":
                next_sp.status = "pending"

    db.commit()
    for r in records:
        db.refresh(r)
    return records


@router.post("/scenes/{scene_id}/reject", response_model=list[ReviewRecordRead])
def reject_scene(scene_id: int, payload: RejectRequest, db: Session = Depends(get_db)) -> list[ReviewRecord]:
    scene = db.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")

    stmt = select(StageProgress).where(StageProgress.scene_id == scene_id, StageProgress.stage_key == payload.stage_key)
    sp = db.scalar(stmt)
    if not sp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="StageProgress not found")

    if sp.status != "reviewing":
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Stage is not under review")

    from_status = sp.status
    sp.status = "rejected"
    sp.reviewer_id = payload.user_id

    record = ReviewRecord(
        project_id=scene.project_id,
        scene_id=scene_id,
        stage_progress_id=sp.id,
        stage_key=payload.stage_key,
        action="reject",
        from_status=from_status,
        to_status="rejected",
        operator_id=payload.user_id,
        comment=payload.comment,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return [record]


@router.get("/scenes/{scene_id}/records", response_model=list[ReviewRecordRead])
def list_review_records(scene_id: int, db: Session = Depends(get_db)) -> list[ReviewRecord]:
    stmt = select(ReviewRecord).where(ReviewRecord.scene_id == scene_id).order_by(ReviewRecord.id.desc())
    return list(db.scalars(stmt).all())

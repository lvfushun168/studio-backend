"""Workflow service layer for stage progression and review logic."""

from datetime import datetime, timezone
from typing import Literal

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.stage_templates import STAGE_TEMPLATES
from app.models.asset import Asset
from app.models.notification import Notification
from app.models.scene import Scene, StageProgress
from app.models.workflow import ReviewRecord


def _get_template_keys(stage_template: str) -> list[str]:
    return [item["key"] for item in STAGE_TEMPLATES.get(stage_template, STAGE_TEMPLATES["ai_single_frame"])]


def _is_layout_stage(stage_key: str) -> bool:
    return stage_key in ("layout_character", "layout_background")


def _get_unlock_targets(scene: Scene, stage_key: str) -> list[str]:
    keys = _get_template_keys(scene.stage_template)
    try:
        current_idx = keys.index(stage_key)
    except ValueError:
        return []

    if (
        stage_key == "storyboard"
        and "layout_character" in keys
        and "layout_background" in keys
    ):
        return ["layout_character", "layout_background"]

    if current_idx + 1 < len(keys):
        return [keys[current_idx + 1]]
    return []


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


def _find_previous_stage_key(scene: Scene, current_key: str) -> str | None:
    keys = _get_template_keys(scene.stage_template)
    try:
        idx = keys.index(current_key)
    except ValueError:
        return None
    if idx <= 0:
        return None
    prev = keys[idx - 1]
    # If current is layout_background and previous is layout_character, skip
    if current_key == "layout_background" and prev == "layout_character":
        if idx >= 2:
            return keys[idx - 2]
        return None
    return prev


def _create_notification(
    db: Session,
    project_id: int,
    user_id: int,
    notif_type: str,
    title: str,
    content: str,
    payload: dict | None = None,
) -> None:
    """Create a notification for a user."""
    n = Notification(
        project_id=project_id,
        user_id=user_id,
        type=notif_type,
        title=title,
        content=content,
        status="unread",
        payload_json=payload,
    )
    db.add(n)


def _notify_scene_assignees(
    db: Session,
    scene: Scene,
    notif_type: str,
    title: str,
    content: str,
    payload: dict | None = None,
    exclude_user_id: int | None = None,
) -> None:
    """Notify all scene assignees except the excluded user."""
    from app.models.project import SceneAssignment
    stmt = select(SceneAssignment).where(SceneAssignment.scene_id == scene.id)
    assignments = db.scalars(stmt).all()
    notified = set()
    for a in assignments:
        if a.user_id != exclude_user_id and a.user_id not in notified:
            _create_notification(db, scene.project_id, a.user_id, notif_type, title, content, payload)
            notified.add(a.user_id)


def submit_stage(
    db: Session,
    scene: Scene,
    stage_key: str,
    user_id: int,
) -> ReviewRecord:
    stmt = select(StageProgress).where(
        StageProgress.scene_id == scene.id,
        StageProgress.stage_key == stage_key,
    )
    sp = db.scalar(stmt)
    if not sp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="StageProgress not found")

    if sp.status not in ("pending", "in_progress", "rejected"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot submit from status '{sp.status}'",
        )

    if stage_key != "ai_draw":
        asset_exists = db.scalar(
            select(Asset.id).where(
                Asset.scene_id == scene.id,
                Asset.stage_key == stage_key,
            ).limit(1)
        )
        if asset_exists is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Stage '{stage_key}' has no assets and cannot be submitted",
            )

    from_status = sp.status
    sp.status = "reviewing"
    sp.submitted_at = datetime.now(timezone.utc)
    if sp.started_at is None:
        sp.started_at = datetime.now(timezone.utc)

    db.add(sp)
    db.flush()

    record = ReviewRecord(
        project_id=scene.project_id,
        scene_id=scene.id,
        stage_progress_id=sp.id,
        stage_key=stage_key,
        action="submit",
        from_status=from_status,
        to_status="reviewing",
        operator_id=user_id,
    )
    db.add(record)

    # Notify directors/producers
    from sqlalchemy import select as _select
    from app.models.project import UserProjectMembership
    from app.models.user import User
    stmt_dir = _select(UserProjectMembership).where(
        UserProjectMembership.project_id == scene.project_id,
    )
    for m in db.scalars(stmt_dir).all():
        effective_role = m.role_in_project
        if not effective_role:
            user = db.get(User, m.user_id)
            effective_role = user.role if user else None
        if effective_role not in ("admin", "director", "producer"):
            continue
        _create_notification(
            db,
            scene.project_id,
            m.user_id,
            "review_required",
            f"{scene.name} 的 {stage_key} 等待审批",
            f"镜头 {scene.name} 的 {stage_key} 阶段已提交，等待审批",
            {"scene_id": scene.id, "stage": stage_key},
        )

    db.commit()
    db.refresh(record)
    return record


def approve_stage(
    db: Session,
    scene: Scene,
    stage_key: str,
    user_id: int,
    comment: str | None = None,
) -> list[ReviewRecord]:
    stmt = select(StageProgress).where(
        StageProgress.scene_id == scene.id,
        StageProgress.stage_key == stage_key,
    )
    sp = db.scalar(stmt)
    if not sp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="StageProgress not found")

    if sp.status != "reviewing":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stage is not under review",
        )

    from_status = sp.status
    sp.status = "approved"
    sp.reviewer_id = user_id
    sp.reviewed_at = datetime.now(timezone.utc)
    sp.approved_at = datetime.now(timezone.utc)

    records: list[ReviewRecord] = []
    record = ReviewRecord(
        project_id=scene.project_id,
        scene_id=scene.id,
        stage_progress_id=sp.id,
        stage_key=stage_key,
        action="approve",
        from_status=from_status,
        to_status="approved",
        operator_id=user_id,
        comment=comment,
    )
    db.add(record)
    records.append(record)

    if _is_layout_stage(stage_key):
        next_key = _check_layout_unlock(scene, db)
        if next_key:
            next_stmt = select(StageProgress).where(
                StageProgress.scene_id == scene.id,
                StageProgress.stage_key == next_key,
            )
            next_sp = db.scalar(next_stmt)
            if next_sp and next_sp.status == "locked":
                next_sp.status = "pending"
    else:
        for next_key in _get_unlock_targets(scene, stage_key):
            next_stmt = select(StageProgress).where(
                StageProgress.scene_id == scene.id,
                StageProgress.stage_key == next_key,
            )
            next_sp = db.scalar(next_stmt)
            if next_sp and next_sp.status == "locked":
                next_sp.status = "pending"

    # Notify scene assignees that stage was approved
    _notify_scene_assignees(
        db,
        scene,
        "review",
        f"{scene.name} 的 {stage_key} 已通过",
        f"镜头 {scene.name} 的 {stage_key} 阶段已通过审批",
        {"scene_id": scene.id, "stage": stage_key},
        exclude_user_id=user_id,
    )

    db.commit()
    for r in records:
        db.refresh(r)
    return records


def reject_stage(
    db: Session,
    scene: Scene,
    stage_key: str,
    user_id: int,
    comment: str | None = None,
) -> list[ReviewRecord]:
    stmt = select(StageProgress).where(
        StageProgress.scene_id == scene.id,
        StageProgress.stage_key == stage_key,
    )
    sp = db.scalar(stmt)
    if not sp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="StageProgress not found")

    if sp.status != "reviewing":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Stage is not under review",
        )

    from_status = sp.status
    sp.status = "rejected"
    sp.reviewer_id = user_id
    sp.reviewed_at = datetime.now(timezone.utc)
    sp.rejected_at = datetime.now(timezone.utc)
    sp.comment = comment

    records: list[ReviewRecord] = []
    record = ReviewRecord(
        project_id=scene.project_id,
        scene_id=scene.id,
        stage_progress_id=sp.id,
        stage_key=stage_key,
        action="reject",
        from_status=from_status,
        to_status="rejected",
        operator_id=user_id,
        comment=comment,
    )
    db.add(record)
    records.append(record)

    # Rollback: previous stage becomes "in_progress" again
    prev_key = _find_previous_stage_key(scene, stage_key)
    if prev_key:
        prev_stmt = select(StageProgress).where(
            StageProgress.scene_id == scene.id,
            StageProgress.stage_key == prev_key,
        )
        prev_sp = db.scalar(prev_stmt)
        if prev_sp and prev_sp.status == "approved":
            prev_from = prev_sp.status
            prev_sp.status = "in_progress"
            prev_sp.approved_at = None
            # Create a record for the rollback
            rollback_record = ReviewRecord(
                project_id=scene.project_id,
                scene_id=scene.id,
                stage_progress_id=prev_sp.id,
                stage_key=prev_key,
                action="rollback",
                from_status=prev_from,
                to_status="in_progress",
                operator_id=user_id,
                comment=f"Auto-rollback due to rejection of {stage_key}",
            )
            db.add(rollback_record)
            records.append(rollback_record)

    # Notify assignees about rejection
    _notify_scene_assignees(
        db,
        scene,
        "review",
        f"{scene.name} 的 {stage_key} 被驳回",
        f"镜头 {scene.name} 的 {stage_key} 阶段被驳回" + (f"：{comment}" if comment else ""),
        {"scene_id": scene.id, "stage": stage_key},
        exclude_user_id=user_id,
    )

    db.commit()
    for r in records:
        db.refresh(r)
    return records


def resubmit_stage(
    db: Session,
    scene: Scene,
    stage_key: str,
    user_id: int,
) -> ReviewRecord:
    """Resubmit a rejected stage after corrections."""
    stmt = select(StageProgress).where(
        StageProgress.scene_id == scene.id,
        StageProgress.stage_key == stage_key,
    )
    sp = db.scalar(stmt)
    if not sp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="StageProgress not found")

    if sp.status != "rejected":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Can only resubmit a rejected stage",
        )

    from_status = sp.status
    sp.status = "reviewing"
    sp.submitted_at = datetime.now(timezone.utc)
    sp.comment = None  # Clear previous rejection comment

    db.add(sp)
    db.flush()

    record = ReviewRecord(
        project_id=scene.project_id,
        scene_id=scene.id,
        stage_progress_id=sp.id,
        stage_key=stage_key,
        action="resubmit",
        from_status=from_status,
        to_status="reviewing",
        operator_id=user_id,
    )
    db.add(record)

    # Notify directors/producers about resubmission
    from sqlalchemy import select as _select2
    from app.models.project import UserProjectMembership
    from app.models.user import User
    stmt_dir = _select2(UserProjectMembership).where(
        UserProjectMembership.project_id == scene.project_id,
    )
    for m in db.scalars(stmt_dir).all():
        effective_role = m.role_in_project
        if not effective_role:
            user = db.get(User, m.user_id)
            effective_role = user.role if user else None
        if effective_role not in ("admin", "director", "producer"):
            continue
        _create_notification(
            db,
            scene.project_id,
            m.user_id,
            "review_required",
            f"{scene.name} 的 {stage_key} 重新提交",
            f"镜头 {scene.name} 的 {stage_key} 阶段已重新提交，等待审批",
            {"scene_id": scene.id, "stage": stage_key},
        )

    db.commit()
    db.refresh(record)
    return record

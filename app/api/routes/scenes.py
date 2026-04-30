from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.auth import (
    CurrentUser,
    require_project_access,
    DIRECTOR_ROLES,
    DIRECTOR_PRODUCER_ROLES,
    ARTIST_ROLES,
    require_role,
    is_project_member,
)
from app.core.database import get_db
from app.domains.stage_templates import build_default_stage_progress
from app.models.project import SceneAssignment, SceneGroup
from app.models.asset import Asset
from app.models.scene import Scene, StageProgress
from app.schemas.scene import (
    SceneAssignmentRead,
    SceneBatchSortRequest,
    SceneCreate,
    SceneRead,
    SceneUpdate,
    StageProgressRead,
)

router = APIRouter()


@router.get("/matrix")
def get_scene_matrix(
    project_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    """Return scenes grouped by scene_group for matrix view."""
    require_project_access(project_id, current_user, db)
    stmt = (
        select(Scene)
        .options(selectinload(Scene.stage_progresses), selectinload(Scene.assignments))
        .where(Scene.project_id == project_id)
        .order_by(Scene.scene_group_id.asc(), Scene.sort_order.asc(), Scene.id.asc())
    )
    scenes = list(db.scalars(stmt).all())
    groups_stmt = select(SceneGroup).where(SceneGroup.project_id == project_id).order_by(SceneGroup.sort_order)
    group_rows = list(db.scalars(groups_stmt).all())
    groups = {
        g.id: {
            "id": g.id,
            "name": g.name,
            "projectId": g.project_id,
            "episodeId": g.episode_id,
            "sortOrder": g.sort_order,
            "scenes": [],
        }
        for g in group_rows
    }
    for s in scenes:
        if s.scene_group_id in groups:
            groups[s.scene_group_id]["scenes"].append(SceneRead.model_validate(s).model_dump(by_alias=True))

    latest_assets_stmt = (
        select(Asset)
        .where(Asset.project_id == project_id)
        .order_by(
            Asset.scene_id.asc().nulls_last(),
            Asset.scene_group_id.asc().nulls_last(),
            Asset.stage_key.asc(),
            Asset.asset_type.asc(),
            Asset.original_name.asc(),
            Asset.version.desc(),
            Asset.id.desc(),
        )
    )
    latest_assets_map: dict[int, dict[str, dict]] = {}
    seen_keys: set[tuple[int, str, str, str]] = set()
    for asset in db.scalars(latest_assets_stmt).all():
        if asset.scene_id is None:
            continue
        group_key = (asset.scene_id, asset.stage_key, asset.asset_type, asset.original_name)
        if group_key in seen_keys:
            continue
        seen_keys.add(group_key)
        latest_assets_map.setdefault(asset.scene_id, {}).setdefault(asset.stage_key, {
            "id": asset.id,
            "type": asset.stage_key,
            "assetType": asset.asset_type,
            "mediaType": asset.media_type,
            "filename": asset.filename,
            "originalName": asset.original_name,
            "url": asset.public_url,
            "thumbnailUrl": asset.thumbnail_url,
            "version": asset.version,
            "userId": asset.uploaded_by,
            "note": asset.note,
            "isGlobal": asset.is_global,
            "createdAt": asset.created_at.isoformat(),
        })

    scene_payloads = [SceneRead.model_validate(s).model_dump(by_alias=True) for s in scenes]
    for item in scene_payloads:
        item["latestAssets"] = latest_assets_map.get(item["id"], {})

    return {
        "projectId": project_id,
        "groups": list(groups.values()),
        "sceneGroups": list(groups.values()),
        "scenes": scene_payloads,
    }


@router.get("", response_model=list[SceneRead])
def list_scenes(
    project_id: int | None = None,
    scene_group_id: int | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[Scene]:
    stmt = (
        select(Scene)
        .options(selectinload(Scene.stage_progresses), selectinload(Scene.scene_group))
        .order_by(Scene.project_id.asc(), Scene.sort_order.asc(), Scene.id.asc())
    )
    if project_id is not None:
        stmt = stmt.where(Scene.project_id == project_id)
    if scene_group_id is not None:
        stmt = stmt.where(Scene.scene_group_id == scene_group_id)
    scenes = list(db.scalars(stmt).all())
    # Filter by project membership for non-admins
    if current_user and current_user.role != "admin":
        scenes = [s for s in scenes if is_project_member(s.project_id, current_user, db)]
    return scenes


@router.post("", response_model=SceneRead, status_code=status.HTTP_201_CREATED)
def create_scene(
    payload: SceneCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Scene:
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    require_project_access(payload.project_id, current_user, db)
    scene = Scene(
        project_id=payload.project_id,
        scene_group_id=payload.scene_group_id,
        name=payload.name,
        description=payload.description,
        level=payload.level,
        stage_template=payload.stage_template,
        pipeline=payload.pipeline,
        frame_count=payload.frame_count,
        duration_seconds=payload.duration_seconds,
        sort_order=payload.sort_order,
        base_scene_id=payload.base_scene_id,
        created_by=current_user.id,
    )
    db.add(scene)
    db.flush()

    for item in build_default_stage_progress(payload.stage_template, payload.project_id, scene.id):
        db.add(StageProgress(**item))

    db.commit()
    db.refresh(scene)

    stmt = (
        select(Scene)
        .options(selectinload(Scene.stage_progresses))
        .where(Scene.id == scene.id)
    )
    return db.scalar(stmt)


@router.post("/batch-sort", status_code=status.HTTP_204_NO_CONTENT)
def batch_update_scene_sort(
    payload: SceneBatchSortRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    """Batch update sort_order for multiple scenes."""
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    for item in payload.items:
        scene = db.get(Scene, item.scene_id)
        if scene:
            require_project_access(scene.project_id, current_user, db)
            scene.sort_order = item.sort_order
    db.commit()


@router.get("/{scene_id}", response_model=SceneRead)
def get_scene(
    scene_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Scene:
    stmt = (
        select(Scene)
        .options(selectinload(Scene.stage_progresses))
        .where(Scene.id == scene_id)
    )
    scene = db.scalar(stmt)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    require_project_access(scene.project_id, current_user, db)
    return scene


@router.put("/{scene_id}", response_model=SceneRead)
def update_scene(
    scene_id: int,
    payload: SceneUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Scene:
    scene = db.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    require_project_access(scene.project_id, current_user, db)
    if payload.scene_group_id is not None:
        scene.scene_group_id = payload.scene_group_id
    if payload.name is not None:
        scene.name = payload.name
    if payload.description is not None:
        scene.description = payload.description
    if payload.level is not None:
        scene.level = payload.level
    if payload.frame_count is not None:
        scene.frame_count = payload.frame_count
    if payload.duration_seconds is not None:
        scene.duration_seconds = payload.duration_seconds
    if payload.sort_order is not None:
        scene.sort_order = payload.sort_order
    if payload.base_scene_id is not None:
        scene.base_scene_id = payload.base_scene_id
    db.commit()
    db.refresh(scene)

    stmt = (
        select(Scene)
        .options(selectinload(Scene.stage_progresses))
        .where(Scene.id == scene.id)
    )
    return db.scalar(stmt)


@router.delete("/{scene_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scene(
    scene_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    scene = db.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    require_project_access(scene.project_id, current_user, db)
    db.delete(scene)
    db.commit()


# Scene assignments

@router.get("/{scene_id}/assignments", response_model=list[SceneAssignmentRead])
def list_scene_assignments(
    scene_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[SceneAssignment]:
    scene = db.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    require_project_access(scene.project_id, current_user, db)
    stmt = select(SceneAssignment).where(SceneAssignment.scene_id == scene_id)
    return list(db.scalars(stmt).all())


@router.post("/{scene_id}/assignments", response_model=SceneAssignmentRead, status_code=status.HTTP_201_CREATED)
def create_scene_assignment(
    scene_id: int,
    user_id: int,
    stage_key: str | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> SceneAssignment:
    scene = db.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    require_project_access(scene.project_id, current_user, db)
    assignment = SceneAssignment(scene_id=scene_id, user_id=user_id, stage_key=stage_key)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.delete("/{scene_id}/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scene_assignment(
    scene_id: int,
    assignment_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    scene = db.get(Scene, scene_id)
    if scene:
        require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
        require_project_access(scene.project_id, current_user, db)
    assignment = db.get(SceneAssignment, assignment_id)
    if not assignment or assignment.scene_id != scene_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    db.delete(assignment)
    db.commit()


# Stage accept & rollback

@router.post("/{scene_id}/stages/{stage_key}/accept", response_model=dict)
def accept_stage(
    scene_id: int,
    stage_key: str,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    """Artist accepts a pending stage and starts working (pending -> in_progress)."""
    scene = db.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    require_role(ARTIST_ROLES)(current_user)
    require_project_access(scene.project_id, current_user, db)

    stmt = select(StageProgress).where(
        StageProgress.scene_id == scene_id,
        StageProgress.stage_key == stage_key,
    )
    sp = db.scalar(stmt)
    if not sp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="StageProgress not found")

    if sp.status != "pending":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot accept stage with status '{sp.status}'",
        )

    sp.status = "in_progress"
    sp.started_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(sp)
    return {"scene_id": scene_id, "stage_key": stage_key, "status": sp.status}


@router.post("/{scene_id}/stages/{stage_key}/rollback", response_model=dict)
def rollback_stage(
    scene_id: int,
    stage_key: str,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    """Rollback current stage to locked and reopen previous stage for correction."""
    scene = db.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    require_role(DIRECTOR_ROLES)(current_user)
    require_project_access(scene.project_id, current_user, db)

    stmt = select(StageProgress).where(
        StageProgress.scene_id == scene_id,
        StageProgress.stage_key == stage_key,
    )
    sp = db.scalar(stmt)
    if not sp:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="StageProgress not found")

    if sp.status not in ("in_progress", "reviewing", "approved", "rejected"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot rollback stage with status '{sp.status}'",
        )

    from app.domains.stage_templates import STAGE_TEMPLATES
    keys = [item["key"] for item in STAGE_TEMPLATES.get(scene.stage_template, STAGE_TEMPLATES["ai_single_frame"])]
    try:
        idx = keys.index(stage_key)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid stage key")

    if idx <= 0:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot rollback the first stage")

    # Lock current stage
    sp.status = "locked"
    db.add(sp)

    # Reopen previous stage
    prev_key = keys[idx - 1]
    if stage_key == "layout_background" and prev_key == "layout_character":
        if idx >= 2:
            prev_key = keys[idx - 2]

    prev_stmt = select(StageProgress).where(
        StageProgress.scene_id == scene_id,
        StageProgress.stage_key == prev_key,
    )
    prev_sp = db.scalar(prev_stmt)
    if prev_sp:
        prev_sp.status = "in_progress"
        prev_sp.approved_at = None
        db.add(prev_sp)

    db.commit()
    return {
        "scene_id": scene_id,
        "stage_key": stage_key,
        "status": "locked",
        "previous_stage": prev_key,
        "previous_status": "in_progress",
    }

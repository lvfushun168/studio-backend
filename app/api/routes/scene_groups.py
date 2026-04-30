from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_project_access
from app.core.database import get_db
from app.models.project import SceneGroup
from app.schemas.scene_group import SceneGroupCreate, SceneGroupRead

router = APIRouter()


@router.get("", response_model=list[SceneGroupRead])
def list_scene_groups(
    project_id: int | None = None,
    episode_id: int | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[SceneGroup]:
    stmt = select(SceneGroup).order_by(SceneGroup.sort_order, SceneGroup.id)
    if project_id is not None:
        stmt = stmt.where(SceneGroup.project_id == project_id)
    if episode_id is not None:
        stmt = stmt.where(SceneGroup.episode_id == episode_id)
    return list(db.scalars(stmt).all())


@router.post("", response_model=SceneGroupRead, status_code=status.HTTP_201_CREATED)
def create_scene_group(
    payload: SceneGroupCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> SceneGroup:
    require_project_access(payload.project_id, current_user, db)
    group = SceneGroup(
        project_id=payload.project_id,
        episode_id=payload.episode_id,
        name=payload.name,
        sort_order=payload.sort_order,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@router.get("/{group_id}", response_model=SceneGroupRead)
def get_scene_group(
    group_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> SceneGroup:
    group = db.get(SceneGroup, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SceneGroup not found")
    require_project_access(group.project_id, current_user, db)
    return group


@router.put("/{group_id}", response_model=SceneGroupRead)
def update_scene_group(
    group_id: int,
    payload: SceneGroupCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> SceneGroup:
    group = db.get(SceneGroup, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SceneGroup not found")
    require_project_access(group.project_id, current_user, db)
    group.name = payload.name
    group.sort_order = payload.sort_order
    db.commit()
    db.refresh(group)
    return group


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scene_group(
    group_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    group = db.get(SceneGroup, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="SceneGroup not found")
    require_project_access(group.project_id, current_user, db)
    db.delete(group)
    db.commit()

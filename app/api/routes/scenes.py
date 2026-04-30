from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.domains.stage_templates import build_default_stage_progress
from app.models.project import SceneAssignment
from app.models.scene import Scene, StageProgress
from app.schemas.scene import SceneAssignmentRead, SceneCreate, SceneRead, SceneUpdate

router = APIRouter()


@router.get("", response_model=list[SceneRead])
def list_scenes(
    project_id: int | None = None,
    scene_group_id: int | None = None,
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
    return list(db.scalars(stmt).all())


@router.post("", response_model=SceneRead, status_code=status.HTTP_201_CREATED)
def create_scene(payload: SceneCreate, db: Session = Depends(get_db)) -> Scene:
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
        created_by=payload.created_by,
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


@router.get("/{scene_id}", response_model=SceneRead)
def get_scene(scene_id: int, db: Session = Depends(get_db)) -> Scene:
    stmt = (
        select(Scene)
        .options(selectinload(Scene.stage_progresses))
        .where(Scene.id == scene_id)
    )
    scene = db.scalar(stmt)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    return scene


@router.put("/{scene_id}", response_model=SceneRead)
def update_scene(scene_id: int, payload: SceneUpdate, db: Session = Depends(get_db)) -> Scene:
    scene = db.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
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
def delete_scene(scene_id: int, db: Session = Depends(get_db)) -> None:
    scene = db.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    db.delete(scene)
    db.commit()


# Scene assignments
@router.get("/{scene_id}/assignments", response_model=list[SceneAssignmentRead])
def list_scene_assignments(scene_id: int, db: Session = Depends(get_db)) -> list[SceneAssignment]:
    stmt = select(SceneAssignment).where(SceneAssignment.scene_id == scene_id)
    return list(db.scalars(stmt).all())


@router.post("/{scene_id}/assignments", response_model=SceneAssignmentRead, status_code=status.HTTP_201_CREATED)
def create_scene_assignment(
    scene_id: int, user_id: int, stage_key: str | None = None, db: Session = Depends(get_db)
) -> SceneAssignment:
    assignment = SceneAssignment(scene_id=scene_id, user_id=user_id, stage_key=stage_key)
    db.add(assignment)
    db.commit()
    db.refresh(assignment)
    return assignment


@router.delete("/{scene_id}/assignments/{assignment_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_scene_assignment(scene_id: int, assignment_id: int, db: Session = Depends(get_db)) -> None:
    assignment = db.get(SceneAssignment, assignment_id)
    if not assignment or assignment.scene_id != scene_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Assignment not found")
    db.delete(assignment)
    db.commit()

from fastapi import APIRouter, Depends, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.database import get_db
from app.domains.stage_templates import build_default_stage_progress
from app.models.scene import Scene, StageProgress
from app.schemas.scene import SceneCreate, SceneRead


router = APIRouter()


@router.get("", response_model=list[SceneRead])
def list_scenes(db: Session = Depends(get_db)) -> list[Scene]:
    stmt = (
        select(Scene)
        .options(selectinload(Scene.stage_progresses))
        .order_by(Scene.project_id.asc(), Scene.sort_order.asc(), Scene.id.asc())
    )
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
        created_by=payload.created_by,
    )
    db.add(scene)
    db.flush()

    for item in build_default_stage_progress(payload.stage_template, payload.project_id, scene.id):
        db.add(StageProgress(**item))

    db.commit()
    db.refresh(scene)

    stmt = select(Scene).options(selectinload(Scene.stage_progresses)).where(Scene.id == scene.id)
    return db.scalar(stmt)

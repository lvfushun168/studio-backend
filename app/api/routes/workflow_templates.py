from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, DIRECTOR_PRODUCER_ROLES, require_project_access, require_role
from app.core.database import get_db
from app.domains.stage_templates import (
    make_project_template_key,
    resolve_stage_template_steps,
    stage_template_exists,
    validate_stage_steps,
)
from app.models.scene import Scene
from app.models.workflow import WorkflowTemplate
from app.schemas.system import StageTemplateItem
from app.schemas.workflow_template import (
    WorkflowTemplateCreate,
    WorkflowTemplateRead,
    WorkflowTemplateUpdate,
)

router = APIRouter()


def _serialize_template(db: Session, template: WorkflowTemplate) -> WorkflowTemplateRead:
    scene_count = db.scalar(
        select(func.count(Scene.id))
        .where(
            Scene.project_id == template.project_id,
            Scene.stage_template == make_project_template_key(template.id),
        )
    )
    return WorkflowTemplateRead(
        id=template.id,
        project_id=template.project_id,
        name=template.name,
        description=template.description,
        based_on_template_key=template.based_on_template_key,
        is_default=template.is_default,
        is_active=template.is_active,
        created_by=template.created_by,
        template_key=make_project_template_key(template.id),
        steps=[StageTemplateItem(**step) for step in template.steps_json or []],
        scene_count=scene_count or 0,
        step_structure_locked=(scene_count or 0) > 0,
    )


def _sync_default_flag(db: Session, project_id: int, template_id: int, should_be_default: bool) -> None:
    if not should_be_default:
        return
    stmt = select(WorkflowTemplate).where(WorkflowTemplate.project_id == project_id)
    for row in db.scalars(stmt).all():
        row.is_default = row.id == template_id


@router.get("", response_model=list[WorkflowTemplateRead])
def list_workflow_templates(
    project_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[WorkflowTemplateRead]:
    require_project_access(project_id, current_user, db)
    stmt = (
        select(WorkflowTemplate)
        .where(WorkflowTemplate.project_id == project_id)
        .order_by(WorkflowTemplate.is_default.desc(), WorkflowTemplate.id.asc())
    )
    return [_serialize_template(db, item) for item in db.scalars(stmt).all()]


@router.post("", response_model=WorkflowTemplateRead, status_code=status.HTTP_201_CREATED)
def create_workflow_template(
    payload: WorkflowTemplateCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> WorkflowTemplateRead:
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    require_project_access(payload.project_id, current_user, db)

    if payload.steps is None:
        if not payload.based_on_template_key:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Either steps or based_on_template_key is required")
        if not stage_template_exists(db, payload.based_on_template_key, payload.project_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Base workflow template not found")
        steps = resolve_stage_template_steps(db, payload.based_on_template_key, payload.project_id)
    else:
        steps = [item.model_dump() for item in payload.steps]
    normalized_steps = validate_stage_steps(steps)

    template = WorkflowTemplate(
        project_id=payload.project_id,
        name=payload.name,
        description=payload.description,
        based_on_template_key=payload.based_on_template_key,
        is_default=payload.is_default,
        is_active=payload.is_active,
        steps_json=normalized_steps,
        created_by=current_user.id,
    )
    db.add(template)
    db.flush()
    _sync_default_flag(db, payload.project_id, template.id, payload.is_default)
    db.commit()
    db.refresh(template)
    return _serialize_template(db, template)


@router.put("/{template_id}", response_model=WorkflowTemplateRead)
def update_workflow_template(
    template_id: int,
    payload: WorkflowTemplateUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> WorkflowTemplateRead:
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    template = db.get(WorkflowTemplate, template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow template not found")
    require_project_access(template.project_id, current_user, db)

    if payload.name is not None:
        template.name = payload.name
    if payload.description is not None:
        template.description = payload.description
    if payload.is_active is not None:
        template.is_active = payload.is_active
    if payload.is_default is not None:
        template.is_default = payload.is_default

    if payload.steps is not None:
        next_steps = validate_stage_steps([item.model_dump() for item in payload.steps])
        scene_stmt = select(Scene).where(Scene.project_id == template.project_id, Scene.stage_template == make_project_template_key(template.id))
        scenes = list(db.scalars(scene_stmt).all())
        if scenes and next_steps != (template.steps_json or []):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Workflow template steps cannot be changed after scenes have been created with this template",
            )
        template.steps_json = next_steps

    _sync_default_flag(db, template.project_id, template.id, bool(template.is_default))
    db.commit()
    db.refresh(template)
    return _serialize_template(db, template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow_template(
    template_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    template = db.get(WorkflowTemplate, template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow template not found")
    require_project_access(template.project_id, current_user, db)

    scene_exists = db.scalar(
        select(Scene.id).where(
            Scene.project_id == template.project_id,
            Scene.stage_template == make_project_template_key(template.id),
        ).limit(1)
    )
    if scene_exists is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Workflow template is already in use by scenes and cannot be deleted")

    db.delete(template)
    db.commit()

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, PRODUCER_ROLES, require_project_access, require_role
from app.core.database import get_db
from app.domains.stage_templates import (
    make_global_template_key,
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


def _normalize_scope(scope: str | None) -> str:
    normalized = (scope or "project").strip().lower()
    if normalized not in {"project", "global"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid workflow template scope")
    return normalized


def _ensure_unique_name(
    db: Session,
    *,
    scope: str,
    name: str,
    project_id: int | None,
    exclude_id: int | None = None,
) -> None:
    stmt = select(WorkflowTemplate).where(
        WorkflowTemplate.scope == scope,
        WorkflowTemplate.name == name,
    )
    if scope == "project":
        stmt = stmt.where(WorkflowTemplate.project_id == project_id)
    else:
        stmt = stmt.where(WorkflowTemplate.project_id.is_(None))
    if exclude_id is not None:
        stmt = stmt.where(WorkflowTemplate.id != exclude_id)
    if db.scalar(stmt.limit(1)):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Workflow template name already exists in this scope")


def _serialize_template(db: Session, template: WorkflowTemplate) -> WorkflowTemplateRead:
    template_key = (
        make_global_template_key(template.id)
        if template.scope == "global"
        else make_project_template_key(template.id)
    )
    scene_count = 0
    if template.scope == "project" and template.project_id is not None:
        scene_count = db.scalar(
            select(func.count(Scene.id))
            .where(
                Scene.project_id == template.project_id,
                Scene.stage_template == template_key,
            )
        ) or 0
    return WorkflowTemplateRead(
        id=template.id,
        scope=template.scope,
        project_id=template.project_id,
        name=template.name,
        description=template.description,
        based_on_template_key=template.based_on_template_key,
        is_default=template.is_default,
        is_active=template.is_active,
        created_by=template.created_by,
        template_key=template_key,
        steps=[StageTemplateItem(**step) for step in template.steps_json or []],
        scene_count=scene_count,
        step_structure_locked=scene_count > 0,
    )


def _sync_default_flag(
    db: Session,
    *,
    scope: str,
    project_id: int | None,
    template_id: int,
    should_be_default: bool,
) -> None:
    if not should_be_default:
        return
    stmt = select(WorkflowTemplate).where(WorkflowTemplate.scope == scope)
    if scope == "project":
        stmt = stmt.where(WorkflowTemplate.project_id == project_id)
    else:
        stmt = stmt.where(WorkflowTemplate.project_id.is_(None))
    for row in db.scalars(stmt).all():
        row.is_default = row.id == template_id


@router.get("", response_model=list[WorkflowTemplateRead])
def list_workflow_templates(
    current_user: CurrentUser,
    project_id: int | None = None,
    scope: str | None = None,
    db: Session = Depends(get_db),
) -> list[WorkflowTemplateRead]:
    normalized_scope = _normalize_scope(scope if scope is not None else ("project" if project_id else "global"))
    if normalized_scope == "project":
        if project_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="project_id is required for project workflow templates")
        require_project_access(project_id, current_user, db)
        stmt = select(WorkflowTemplate).where(
            WorkflowTemplate.scope == "project",
            WorkflowTemplate.project_id == project_id,
        )
    else:
        require_role(PRODUCER_ROLES)(current_user)
        stmt = select(WorkflowTemplate).where(
            WorkflowTemplate.scope == "global",
            WorkflowTemplate.project_id.is_(None),
        )
    stmt = stmt.order_by(WorkflowTemplate.is_default.desc(), WorkflowTemplate.id.asc())
    return [_serialize_template(db, item) for item in db.scalars(stmt).all()]


@router.post("", response_model=WorkflowTemplateRead, status_code=status.HTTP_201_CREATED)
def create_workflow_template(
    payload: WorkflowTemplateCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> WorkflowTemplateRead:
    require_role(PRODUCER_ROLES)(current_user)
    normalized_scope = _normalize_scope(payload.scope)
    project_id = payload.project_id
    if normalized_scope == "project":
        if project_id is None:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="project_id is required for project workflow templates")
        require_project_access(project_id, current_user, db)
    else:
        project_id = None

    if payload.steps is None:
        if not payload.based_on_template_key:
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Either steps or based_on_template_key is required")
        if not stage_template_exists(db, payload.based_on_template_key, project_id):
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Base workflow template not found")
        steps = resolve_stage_template_steps(db, payload.based_on_template_key, project_id)
    else:
        steps = [item.model_dump() for item in payload.steps]
    normalized_steps = validate_stage_steps(steps)
    _ensure_unique_name(db, scope=normalized_scope, project_id=project_id, name=payload.name.strip())

    template = WorkflowTemplate(
        scope=normalized_scope,
        project_id=project_id,
        name=payload.name.strip(),
        description=payload.description,
        based_on_template_key=payload.based_on_template_key,
        is_default=payload.is_default,
        is_active=payload.is_active,
        steps_json=normalized_steps,
        created_by=current_user.id,
    )
    db.add(template)
    db.flush()
    _sync_default_flag(db, scope=normalized_scope, project_id=project_id, template_id=template.id, should_be_default=payload.is_default)
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
    require_role(PRODUCER_ROLES)(current_user)
    template = db.get(WorkflowTemplate, template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow template not found")
    if template.scope == "project":
        require_project_access(template.project_id, current_user, db)

    if payload.name is not None:
        next_name = payload.name.strip()
        _ensure_unique_name(db, scope=template.scope, project_id=template.project_id, name=next_name, exclude_id=template.id)
        template.name = next_name
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

    _sync_default_flag(
        db,
        scope=template.scope,
        project_id=template.project_id,
        template_id=template.id,
        should_be_default=bool(template.is_default),
    )
    db.commit()
    db.refresh(template)
    return _serialize_template(db, template)


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_workflow_template(
    template_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    require_role(PRODUCER_ROLES)(current_user)
    template = db.get(WorkflowTemplate, template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Workflow template not found")
    if template.scope == "project":
        require_project_access(template.project_id, current_user, db)

    if template.scope == "project":
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

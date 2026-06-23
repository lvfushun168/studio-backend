from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.auth import ADMIN_ROLES, CurrentUser, PRODUCER_ROLES, get_accessible_project_ids, require_project_access, require_role
from app.core.database import get_db
from app.models.scene import Scene, StageProgress
from app.models.work_step import SceneWorkStep, WorkStepTemplate, WorkStepTemplateItem
from app.schemas.work_step import (
    SceneWorkStepCreate,
    SceneWorkStepRead,
    SceneWorkStepUpdate,
    ApplyWorkStepTemplateRequest,
    BatchApplyWorkStepTemplateRequest,
    StepSubmissionRead,
    StepSubmitRequest,
    WorkStepListRead,
    WorkStepBatchUpdate,
    WorkStepTemplateCopy,
    WorkStepTemplateCreate,
    WorkStepTemplateItemWrite,
    WorkStepTemplateRead,
    WorkStepTemplateUpdate,
)
from app.services.audit_service import record_audit
from app.services import work_step_service
from app.services.work_step_query_service import aggregate_work_step_inputs, list_work_step_tasks
from app.services.work_step_service import ensure_default_for_stage, record_work_step_event, stage_key_exists


template_router = APIRouter()
work_step_router = APIRouter()
scene_stage_router = APIRouter()


def _get_template(db: Session, template_id: int) -> WorkStepTemplate:
    template = db.scalar(
        select(WorkStepTemplate)
        .options(selectinload(WorkStepTemplate.items))
        .where(WorkStepTemplate.id == template_id)
    )
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work step template not found")
    return template


def _authorize_template_write(template_scope: str, project_id: int | None, current_user: CurrentUser, db: Session) -> None:
    require_role(PRODUCER_ROLES)(current_user)
    if template_scope == "system":
        require_role(ADMIN_ROLES)(current_user)
    elif project_id is not None:
        require_project_access(project_id, current_user, db)


def _ensure_template_identity_unique(
    db: Session,
    *,
    scope: str,
    project_id: int | None,
    stage_key: str,
    name: str,
    version: int,
    exclude_id: int | None = None,
) -> None:
    stmt = select(WorkStepTemplate.id).where(
        WorkStepTemplate.scope == scope,
        WorkStepTemplate.stage_key == stage_key,
        WorkStepTemplate.name == name,
        WorkStepTemplate.version == version,
    )
    stmt = stmt.where(
        WorkStepTemplate.project_id == project_id
        if project_id is not None
        else WorkStepTemplate.project_id.is_(None)
    )
    if exclude_id is not None:
        stmt = stmt.where(WorkStepTemplate.id != exclude_id)
    if db.scalar(stmt.limit(1)) is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Work step template version already exists")


def _sync_default_template(db: Session, template: WorkStepTemplate) -> None:
    if not template.is_default:
        return
    stmt = select(WorkStepTemplate).where(
        WorkStepTemplate.scope == template.scope,
        WorkStepTemplate.stage_key == template.stage_key,
        WorkStepTemplate.id != template.id,
    )
    stmt = stmt.where(
        WorkStepTemplate.project_id == template.project_id
        if template.project_id is not None
        else WorkStepTemplate.project_id.is_(None)
    )
    for other in db.scalars(stmt).all():
        other.is_default = False


def _replace_template_items(template: WorkStepTemplate, items: list[WorkStepTemplateItemWrite]) -> None:
    existing = {item.step_key: item for item in template.items}
    next_items: list[WorkStepTemplateItem] = []
    for payload in items:
        item = existing.pop(payload.step_key, None) or WorkStepTemplateItem(step_key=payload.step_key)
        for field, value in payload.model_dump().items():
            setattr(item, field, value)
        next_items.append(item)
    template.items = next_items


@template_router.get("", response_model=list[WorkStepTemplateRead])
def list_work_step_templates(
    current_user: CurrentUser,
    project_id: int | None = None,
    stage_key: str | None = None,
    scope: str | None = None,
    include_inactive: bool = False,
    db: Session = Depends(get_db),
) -> list[WorkStepTemplate]:
    if scope not in {None, "system", "project"}:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid template scope")
    if project_id is not None:
        require_project_access(project_id, current_user, db)
    elif scope != "system":
        require_role(PRODUCER_ROLES)(current_user)

    stmt = select(WorkStepTemplate).options(selectinload(WorkStepTemplate.items))
    if project_id is not None:
        stmt = stmt.where(WorkStepTemplate.project_id == project_id)
    if stage_key:
        stmt = stmt.where(WorkStepTemplate.stage_key == stage_key)
    if scope:
        stmt = stmt.where(WorkStepTemplate.scope == scope)
    if not include_inactive:
        stmt = stmt.where(WorkStepTemplate.is_active.is_(True))
    stmt = stmt.order_by(
        WorkStepTemplate.stage_key,
        WorkStepTemplate.is_default.desc(),
        WorkStepTemplate.version.desc(),
        WorkStepTemplate.id,
    )
    return list(db.scalars(stmt).unique().all())


@template_router.post("", response_model=WorkStepTemplateRead, status_code=status.HTTP_201_CREATED)
def create_work_step_template(
    payload: WorkStepTemplateCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> WorkStepTemplate:
    _authorize_template_write(payload.scope, payload.project_id, current_user, db)
    if not stage_key_exists(db, payload.stage_key, payload.project_id):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="stageKey does not exist in a workflow template")
    _ensure_template_identity_unique(
        db,
        scope=payload.scope,
        project_id=payload.project_id,
        stage_key=payload.stage_key,
        name=payload.name,
        version=payload.version,
    )
    template = WorkStepTemplate(
        scope=payload.scope,
        project_id=payload.project_id,
        name=payload.name,
        description=payload.description,
        stage_key=payload.stage_key,
        version=payload.version,
        is_default=payload.is_default,
        is_active=payload.is_active,
        created_by=current_user.id,
    )
    db.add(template)
    _replace_template_items(template, payload.items)
    db.flush()
    _sync_default_template(db, template)
    record_audit(
        db,
        user_id=current_user.id,
        action="work_step_template.create",
        target_type="work_step_template",
        target_id=template.id,
        project_id=template.project_id,
        summary=f"创建工作步骤模板 {template.name}",
        payload_json={"stageKey": template.stage_key, "version": template.version},
    )
    db.commit()
    return _get_template(db, template.id)


@template_router.put("/{template_id}", response_model=WorkStepTemplateRead)
def update_work_step_template(
    template_id: int,
    payload: WorkStepTemplateUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> WorkStepTemplate:
    template = _get_template(db, template_id)
    _authorize_template_write(template.scope, template.project_id, current_user, db)
    next_name = payload.name if payload.name is not None else template.name
    next_version = payload.version if payload.version is not None else template.version
    _ensure_template_identity_unique(
        db,
        scope=template.scope,
        project_id=template.project_id,
        stage_key=template.stage_key,
        name=next_name,
        version=next_version,
        exclude_id=template.id,
    )
    before = {"name": template.name, "version": template.version, "isDefault": template.is_default, "isActive": template.is_active}
    for field in payload.model_fields_set & {"name", "description", "version", "is_default", "is_active"}:
        setattr(template, field, getattr(payload, field))
    if payload.items is not None:
        _replace_template_items(template, payload.items)
    _sync_default_template(db, template)
    record_audit(
        db,
        user_id=current_user.id,
        action="work_step_template.update",
        target_type="work_step_template",
        target_id=template.id,
        project_id=template.project_id,
        summary=f"更新工作步骤模板 {template.name}",
        payload_json={"before": before},
    )
    db.commit()
    return _get_template(db, template.id)


@template_router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_work_step_template(
    template_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Response:
    template = _get_template(db, template_id)
    _authorize_template_write(template.scope, template.project_id, current_user, db)
    template.is_active = False
    template.is_default = False
    record_audit(
        db,
        user_id=current_user.id,
        action="work_step_template.deactivate",
        target_type="work_step_template",
        target_id=template.id,
        project_id=template.project_id,
        summary=f"停用工作步骤模板 {template.name}",
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@template_router.post("/{template_id}/copy", response_model=WorkStepTemplateRead, status_code=status.HTTP_201_CREATED)
def copy_work_step_template(
    template_id: int,
    payload: WorkStepTemplateCopy,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> WorkStepTemplate:
    source = _get_template(db, template_id)
    target_scope = "project" if payload.project_id is not None else source.scope
    target_project_id = payload.project_id if target_scope == "project" else None
    _authorize_template_write(target_scope, target_project_id, current_user, db)
    next_name = payload.name or source.name
    next_version = payload.version or (source.version + 1)
    _ensure_template_identity_unique(
        db,
        scope=target_scope,
        project_id=target_project_id,
        stage_key=source.stage_key,
        name=next_name,
        version=next_version,
    )
    copied = WorkStepTemplate(
        scope=target_scope,
        project_id=target_project_id,
        name=next_name,
        description=source.description,
        stage_key=source.stage_key,
        version=next_version,
        is_default=payload.is_default,
        is_active=True,
        created_by=current_user.id,
    )
    copied.items = [
        WorkStepTemplateItem(
            step_key=item.step_key,
            name=item.name,
            description=item.description,
            sort_order=item.sort_order,
            is_required=item.is_required,
            allow_parallel=item.allow_parallel,
            default_duration_hours=item.default_duration_hours,
            default_role=item.default_role,
            metadata_json=dict(item.metadata_json) if item.metadata_json else None,
        )
        for item in source.items
    ]
    db.add(copied)
    db.flush()
    _sync_default_template(db, copied)
    db.commit()
    return _get_template(db, copied.id)


def _get_scene_stage(db: Session, scene_id: int, stage_key: str) -> tuple[Scene, StageProgress]:
    scene = db.get(Scene, scene_id)
    if not scene:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
    stage_progress = db.scalar(
        select(StageProgress).where(StageProgress.scene_id == scene_id, StageProgress.stage_key == stage_key)
    )
    if not stage_progress:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene stage not found")
    return scene, stage_progress


@work_step_router.get("", response_model=WorkStepListRead)
def list_work_steps(
    current_user: CurrentUser,
    project_id: int | None = None,
    episode_id: int | None = None,
    scene_group_id: int | None = None,
    scene_id: int | None = None,
    stage_key: str | None = None,
    assignee_id: int | None = None,
    mine_only: bool = False,
    work_step_status: list[str] | None = Query(default=None, alias="status"),
    overdue_only: bool = False,
    blocked_only: bool = False,
    unassigned_only: bool = False,
    priority: str | None = None,
    keyword: str | None = None,
    include_cancelled: bool = False,
    db: Session = Depends(get_db),
) -> WorkStepListRead:
    if project_id is None and scene_id is None and not mine_only:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="project_id or scene_id is required")
    if scene_id is not None:
        scene = db.get(Scene, scene_id)
        if not scene:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Scene not found")
        project_id = scene.project_id
    if project_id is not None:
        require_project_access(project_id, current_user, db)
    project_ids = None if project_id is not None or current_user.role == "admin" else get_accessible_project_ids(current_user, db)
    return WorkStepListRead(**list_work_step_tasks(
        db,
        project_id=project_id,
        project_ids=project_ids,
        episode_id=episode_id,
        scene_group_id=scene_group_id,
        scene_id=scene_id,
        stage_key=stage_key,
        assignee_id=current_user.id if mine_only else assignee_id,
        statuses=work_step_status,
        overdue_only=overdue_only,
        blocked_only=blocked_only,
        unassigned_only=unassigned_only,
        priority=priority,
        keyword=keyword,
        include_cancelled=include_cancelled,
    ))


@work_step_router.post("/batch-update", response_model=list[SceneWorkStepRead])
def batch_update_scene_work_steps(
    payload: WorkStepBatchUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[SceneWorkStep]:
    require_role(PRODUCER_ROLES)(current_user)
    unique_ids = list(dict.fromkeys(payload.work_step_ids))
    steps = list(db.scalars(select(SceneWorkStep).where(SceneWorkStep.id.in_(unique_ids))).all())
    if len(steps) != len(unique_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more work steps were not found")
    for project_id in {item.project_id for item in steps}:
        require_project_access(project_id, current_user, db)
    changes = {
        field: getattr(payload, field)
        for field in payload.model_fields_set
        if field != "work_step_ids"
    }
    if not changes:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="At least one update field is required")
    updated = work_step_service.batch_update_work_steps(db, unique_ids, changes, current_user.id)
    db.commit()
    for item in updated:
        db.refresh(item)
    return updated


@work_step_router.post("/batch-apply-template")
def batch_apply_work_step_template(
    payload: BatchApplyWorkStepTemplateRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    require_role(PRODUCER_ROLES)(current_user)
    previews = []
    seen_targets = set()
    for target in payload.targets:
        key = (target.scene_id, target.stage_key)
        if key in seen_targets:
            continue
        seen_targets.add(key)
        scene, stage_progress = _get_scene_stage(db, target.scene_id, target.stage_key)
        require_project_access(scene.project_id, current_user, db)
        if payload.preview_only:
            _, preview = work_step_service.preview_template_application(
                db, scene, stage_progress, payload.template_id, payload.mode
            )
        else:
            preview = work_step_service.apply_template_to_stage(
                db, scene, stage_progress, payload.template_id, payload.mode, current_user.id
            )
        previews.append(preview)
    if not payload.preview_only:
        db.commit()
    return {"previewOnly": payload.preview_only, "items": previews, "targetCount": len(previews)}


@scene_stage_router.get("/{scene_id}/stages/{stage_key}/work-steps", response_model=list[SceneWorkStepRead])
def list_stage_work_steps(
    scene_id: int,
    stage_key: str,
    current_user: CurrentUser,
    include_cancelled: bool = False,
    db: Session = Depends(get_db),
) -> list[SceneWorkStep]:
    scene, stage_progress = _get_scene_stage(db, scene_id, stage_key)
    require_project_access(scene.project_id, current_user, db)
    ensure_default_for_stage(db, scene, stage_progress, current_user.id)
    db.commit()
    stmt = select(SceneWorkStep).where(SceneWorkStep.scene_id == scene_id, SceneWorkStep.stage_key == stage_key)
    if not include_cancelled:
        stmt = stmt.where(SceneWorkStep.status != "cancelled")
    return list(db.scalars(stmt.order_by(SceneWorkStep.sort_order, SceneWorkStep.id)).all())


@scene_stage_router.post("/{scene_id}/stages/{stage_key}/work-steps", response_model=SceneWorkStepRead, status_code=status.HTTP_201_CREATED)
def create_scene_work_step(
    scene_id: int,
    stage_key: str,
    payload: SceneWorkStepCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> SceneWorkStep:
    require_role(PRODUCER_ROLES)(current_user)
    scene, stage_progress = _get_scene_stage(db, scene_id, stage_key)
    require_project_access(scene.project_id, current_user, db)
    if stage_progress.status in {"reviewing", "approved"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Work step structure is locked while the stage is reviewing or approved")
    duplicate = db.scalar(
        select(SceneWorkStep.id).where(
            SceneWorkStep.scene_id == scene_id,
            SceneWorkStep.stage_key == stage_key,
            SceneWorkStep.step_key == payload.step_key,
        ).limit(1)
    )
    if duplicate is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="stepKey already exists in this scene stage")
    has_active = db.scalar(
        select(SceneWorkStep.id).where(
            SceneWorkStep.scene_id == scene_id,
            SceneWorkStep.stage_key == stage_key,
            SceneWorkStep.status != "cancelled",
        ).limit(1)
    ) is not None
    initial_status = "not_ready" if stage_progress.status == "locked" else ("todo" if payload.allow_parallel or not has_active else "not_ready")
    work_step = SceneWorkStep(
        project_id=scene.project_id,
        scene_group_id=scene.scene_group_id,
        scene_id=scene.id,
        stage_progress_id=stage_progress.id,
        stage_key=stage_key,
        original_name=payload.name,
        status=initial_status,
        created_by=current_user.id,
        **payload.model_dump(),
    )
    db.add(work_step)
    db.flush()
    record_work_step_event(db, work_step, current_user.id, "step.create", to_status=initial_status)
    db.commit()
    db.refresh(work_step)
    return work_step


@scene_stage_router.post("/{scene_id}/stages/{stage_key}/work-steps/apply-template")
def apply_work_step_template(
    scene_id: int,
    stage_key: str,
    payload: ApplyWorkStepTemplateRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    require_role(PRODUCER_ROLES)(current_user)
    scene, stage_progress = _get_scene_stage(db, scene_id, stage_key)
    require_project_access(scene.project_id, current_user, db)
    if payload.preview_only:
        _, preview = work_step_service.preview_template_application(
            db, scene, stage_progress, payload.template_id, payload.mode
        )
        return {"previewOnly": True, **preview}
    preview = work_step_service.apply_template_to_stage(
        db, scene, stage_progress, payload.template_id, payload.mode, current_user.id
    )
    db.commit()
    return {"previewOnly": False, **preview}


def _get_work_step(db: Session, work_step_id: int) -> SceneWorkStep:
    work_step = db.get(SceneWorkStep, work_step_id)
    if not work_step:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work step not found")
    return work_step


@work_step_router.get("/{work_step_id}", response_model=SceneWorkStepRead)
def get_scene_work_step(
    work_step_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> SceneWorkStep:
    work_step = _get_work_step(db, work_step_id)
    require_project_access(work_step.project_id, current_user, db)
    return work_step


@work_step_router.get("/{work_step_id}/submissions", response_model=list[StepSubmissionRead])
def list_step_submissions(
    work_step_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    work_step = _get_work_step(db, work_step_id)
    require_project_access(work_step.project_id, current_user, db)
    return work_step_service.list_submissions(db, work_step.id)


@work_step_router.get("/{work_step_id}/input-assets")
def get_work_step_input_assets(
    work_step_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    work_step = _get_work_step(db, work_step_id)
    require_project_access(work_step.project_id, current_user, db)
    return aggregate_work_step_inputs(db, work_step)


@work_step_router.post("/{work_step_id}/start", response_model=SceneWorkStepRead)
def start_scene_work_step(
    work_step_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> SceneWorkStep:
    work_step = _get_work_step(db, work_step_id)
    require_project_access(work_step.project_id, current_user, db)
    return work_step_service.start_work_step(db, work_step.id, current_user)


@work_step_router.post("/{work_step_id}/submit", response_model=StepSubmissionRead, status_code=status.HTTP_201_CREATED)
def submit_scene_work_step(
    work_step_id: int,
    payload: StepSubmitRequest,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    work_step = _get_work_step(db, work_step_id)
    require_project_access(work_step.project_id, current_user, db)
    return work_step_service.submit_work_step(db, work_step.id, current_user, payload.asset_ids, payload.note)


@work_step_router.post("/{work_step_id}/withdraw", response_model=StepSubmissionRead)
def withdraw_scene_work_step_submission(
    work_step_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
):
    work_step = _get_work_step(db, work_step_id)
    require_project_access(work_step.project_id, current_user, db)
    return work_step_service.withdraw_latest_submission(db, work_step.id, current_user)


@work_step_router.post("/{work_step_id}/cancel", status_code=status.HTTP_204_NO_CONTENT)
def cancel_scene_work_step(
    work_step_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Response:
    work_step = _get_work_step(db, work_step_id)
    require_project_access(work_step.project_id, current_user, db)
    work_step_service.cancel_work_step(db, work_step.id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@work_step_router.patch("/{work_step_id}", response_model=SceneWorkStepRead)
def update_scene_work_step(
    work_step_id: int,
    payload: SceneWorkStepUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> SceneWorkStep:
    require_role(PRODUCER_ROLES)(current_user)
    work_step = _get_work_step(db, work_step_id)
    require_project_access(work_step.project_id, current_user, db)
    stage_progress = db.get(StageProgress, work_step.stage_progress_id)
    if stage_progress and stage_progress.status in {"reviewing", "approved"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Work step cannot be changed while the stage is reviewing or approved")
    if "assignee_id" in payload.model_fields_set:
        work_step_service.validate_assignee(db, work_step.project_id, payload.assignee_id)
    before = {field: getattr(work_step, field) for field in payload.model_fields_set}
    for field in payload.model_fields_set:
        setattr(work_step, field, getattr(payload, field))
    record_work_step_event(
        db,
        work_step,
        current_user.id,
        "step.assign" if "assignee_id" in payload.model_fields_set and before.get("assignee_id") != payload.assignee_id else "step.update",
        payload_json={"before": {key: str(value) if isinstance(value, datetime) else value for key, value in before.items()}},
    )
    db.commit()
    db.refresh(work_step)
    return work_step


@work_step_router.delete("/{work_step_id}", status_code=status.HTTP_204_NO_CONTENT)
def deactivate_scene_work_step(
    work_step_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Response:
    work_step = _get_work_step(db, work_step_id)
    require_project_access(work_step.project_id, current_user, db)
    work_step_service.cancel_work_step(db, work_step.id, current_user)
    return Response(status_code=status.HTTP_204_NO_CONTENT)

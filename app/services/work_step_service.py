from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.domains.stage_templates import STAGE_TEMPLATES
from app.models.asset import Asset
from app.models.project import SceneAssignment, UserProjectMembership
from app.models.scene import Scene, StageProgress
from app.models.workflow import WorkflowTemplate
from app.models.work_step import (
    SceneWorkStep,
    StepSubmission,
    StepSubmissionAsset,
    WorkStepEvent,
    WorkStepTemplate,
)
from app.models.user import User
from app.schemas.scene import SceneWorkStepPlan
from app.services.audit_service import record_audit
from app.services.notification_service import notify_step_schedule_change, notify_users_for_step, project_role_user_ids


DEFAULT_STEP_KEY = "stage_delivery"
DEFAULT_STEP_NAME = "阶段交付"


def stage_key_exists(db: Session, stage_key: str, project_id: int | None = None) -> bool:
    if any(stage_key == item["key"] for stages in STAGE_TEMPLATES.values() for item in stages):
        return True
    stmt = select(WorkflowTemplate).where(WorkflowTemplate.is_active.is_(True))
    if project_id is not None:
        stmt = stmt.where(
            (WorkflowTemplate.scope == "global")
            | (WorkflowTemplate.project_id == project_id)
        )
    for template in db.scalars(stmt).all():
        if any(stage_key == item.get("key") for item in template.steps_json or []):
            return True
    return False


def get_applicable_template(db: Session, project_id: int, stage_key: str) -> WorkStepTemplate | None:
    base = (
        select(WorkStepTemplate)
        .options(selectinload(WorkStepTemplate.items))
        .where(
            WorkStepTemplate.stage_key == stage_key,
            WorkStepTemplate.is_default.is_(True),
            WorkStepTemplate.is_active.is_(True),
        )
        .order_by(WorkStepTemplate.version.desc(), WorkStepTemplate.id.desc())
    )
    project_template = db.scalar(
        base.where(
            WorkStepTemplate.scope == "project",
            WorkStepTemplate.project_id == project_id,
        ).limit(1)
    )
    if project_template:
        return project_template
    return db.scalar(
        base.where(
            WorkStepTemplate.scope == "system",
            WorkStepTemplate.project_id.is_(None),
        ).limit(1)
    )


def _initial_status(stage_status: str, *, index: int) -> str:
    if stage_status == "locked":
        return "not_ready"
    return "todo" if index == 0 else "not_ready"


def record_work_step_event(
    db: Session,
    work_step: SceneWorkStep,
    operator_id: int,
    action: str,
    *,
    from_status: str | None = None,
    to_status: str | None = None,
    comment: str | None = None,
    payload_json: dict | None = None,
) -> WorkStepEvent:
    event = WorkStepEvent(
        project_id=work_step.project_id,
        scene_id=work_step.scene_id,
        scene_work_step_id=work_step.id,
        operator_id=operator_id,
        action=action,
        from_status=from_status,
        to_status=to_status,
        comment=comment,
        payload_json=payload_json,
    )
    db.add(event)
    return event


def _build_from_template(
    scene: Scene,
    stage_progress: StageProgress,
    template: WorkStepTemplate | None,
    operator_id: int,
) -> list[SceneWorkStep]:
    source_items = list(template.items) if template else [None]
    result: list[SceneWorkStep] = []
    for index, item in enumerate(source_items):
        work_step = SceneWorkStep(
            project_id=scene.project_id,
            scene_group_id=scene.scene_group_id,
            scene_id=scene.id,
            stage_progress_id=stage_progress.id,
            stage_key=stage_progress.stage_key,
            template_id=template.id if template else None,
            template_item_id=getattr(item, "id", None) if item else None,
            step_key=item.step_key if item else DEFAULT_STEP_KEY,
            name=item.name if item else DEFAULT_STEP_NAME,
            original_name=item.name if item else DEFAULT_STEP_NAME,
            description=item.description if item else None,
            sort_order=item.sort_order if item else 10,
            is_required=item.is_required if item else True,
            allow_parallel=False,
            status=_initial_status(
                stage_progress.status,
                index=index,
            ),
            priority="normal",
            created_by=operator_id,
            metadata_json=dict(item.metadata_json) if item and item.metadata_json else None,
        )
        result.append(work_step)
    return result


def _build_from_scene(
    db: Session,
    scene: Scene,
    stage_progress: StageProgress,
    source_scene_id: int,
    operator_id: int,
) -> list[SceneWorkStep]:
    source_steps = list(
        db.scalars(
            select(SceneWorkStep)
            .where(
                SceneWorkStep.scene_id == source_scene_id,
                SceneWorkStep.stage_key == stage_progress.stage_key,
                SceneWorkStep.status != "cancelled",
            )
            .order_by(SceneWorkStep.sort_order, SceneWorkStep.id)
        ).all()
    )
    result: list[SceneWorkStep] = []
    for index, source in enumerate(source_steps):
        result.append(
            SceneWorkStep(
                project_id=scene.project_id,
                scene_group_id=scene.scene_group_id,
                scene_id=scene.id,
                stage_progress_id=stage_progress.id,
                stage_key=stage_progress.stage_key,
                template_id=source.template_id,
                template_item_id=source.template_item_id,
                step_key=source.step_key,
                name=source.name,
                original_name=source.original_name or source.name,
                description=source.description,
                sort_order=source.sort_order,
                is_required=source.is_required,
                allow_parallel=False,
                status=_initial_status(stage_progress.status, index=index),
                priority="normal",
                created_by=operator_id,
                metadata_json=dict(source.metadata_json) if source.metadata_json else None,
            )
        )
    return result


def materialize_scene_work_steps(
    db: Session,
    scene: Scene,
    stage_progresses: Iterable[StageProgress],
    operator_id: int,
    *,
    copy_from_scene_id: int | None = None,
    work_step_plans: dict[str, SceneWorkStepPlan] | None = None,
) -> list[SceneWorkStep]:
    if copy_from_scene_id is not None:
        source_scene = db.get(Scene, copy_from_scene_id)
        if not source_scene or source_scene.project_id != scene.project_id:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="copyWorkStepsFromSceneId must reference a scene in the same project",
            )

    created: list[SceneWorkStep] = []
    for stage_progress in stage_progresses:
        steps = (
            _build_from_scene(db, scene, stage_progress, copy_from_scene_id, operator_id)
            if copy_from_scene_id is not None
            else []
        )
        if not steps:
            plan = (work_step_plans or {}).get(stage_progress.stage_key)
            template = None
            if plan and plan.mode == "template":
                template = _get_template_for_scene_plan(db, scene, stage_progress, plan.template_id)
                steps = _build_from_template(scene, stage_progress, template, operator_id)
            elif plan and plan.mode == "manual":
                steps = _build_from_items(scene, stage_progress, plan.items or [], operator_id)
            elif plan and plan.mode == "stage_delivery":
                steps = _build_from_template(scene, stage_progress, None, operator_id)
            else:
                template = get_applicable_template(db, scene.project_id, stage_progress.stage_key)
                if template is None and work_step_plans is not None:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                        detail=f"workStepPlans.{stage_progress.stage_key} is required because this stage has no default template",
                    )
                steps = _build_from_template(scene, stage_progress, template, operator_id)
        db.add_all(steps)
        db.flush()
        for work_step in steps:
            record_work_step_event(
                db,
                work_step,
                operator_id,
                "step.create",
                to_status=work_step.status,
                payload_json={"sourceTemplateId": work_step.template_id},
            )
        created.extend(steps)
    return created


def _get_template_for_scene_plan(
    db: Session,
    scene: Scene,
    stage_progress: StageProgress,
    template_id: int | None,
) -> WorkStepTemplate:
    template = db.scalar(
        select(WorkStepTemplate)
        .options(selectinload(WorkStepTemplate.items))
        .where(WorkStepTemplate.id == template_id, WorkStepTemplate.is_active.is_(True))
    )
    if (
        not template
        or template.stage_key != stage_progress.stage_key
        or (template.scope == "project" and template.project_id != scene.project_id)
        or (template.scope == "system" and template.project_id is not None)
    ):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid work step template for scene stage")
    return template


def _build_from_items(
    scene: Scene,
    stage_progress: StageProgress,
    items,
    operator_id: int,
) -> list[SceneWorkStep]:
    if not items:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Manual work step plan requires at least one item")
    result: list[SceneWorkStep] = []
    for index, item in enumerate(items):
        result.append(
            SceneWorkStep(
                project_id=scene.project_id,
                scene_group_id=scene.scene_group_id,
                scene_id=scene.id,
                stage_progress_id=stage_progress.id,
                stage_key=stage_progress.stage_key,
                step_key=item.step_key,
                name=item.name,
                original_name=item.name,
                description=item.description,
                sort_order=item.sort_order,
                is_required=item.is_required,
                allow_parallel=False,
                status=_initial_status(stage_progress.status, index=index),
                priority="normal",
                created_by=operator_id,
                metadata_json=dict(item.metadata_json) if item.metadata_json else None,
            )
        )
    return result


def ensure_default_for_stage(
    db: Session,
    scene: Scene,
    stage_progress: StageProgress,
    operator_id: int,
) -> SceneWorkStep:
    existing = db.scalar(
        select(SceneWorkStep).where(
            SceneWorkStep.scene_id == scene.id,
            SceneWorkStep.stage_key == stage_progress.stage_key,
        ).limit(1)
    )
    if existing:
        return existing
    work_step = _build_from_template(scene, stage_progress, None, operator_id)[0]
    db.add(work_step)
    db.flush()
    record_work_step_event(db, work_step, operator_id, "step.backfill_default", to_status=work_step.status)
    return work_step


def get_effective_assignee_id(db: Session, work_step: SceneWorkStep) -> int | None:
    if work_step.assignee_id is not None:
        return work_step.assignee_id
    stage_progress = db.get(StageProgress, work_step.stage_progress_id)
    if stage_progress and stage_progress.assignee_id is not None:
        return stage_progress.assignee_id
    stage_assignment = db.scalar(
        select(SceneAssignment.user_id).where(
            SceneAssignment.scene_id == work_step.scene_id,
            SceneAssignment.stage_key == work_step.stage_key,
        ).order_by(SceneAssignment.id).limit(1)
    )
    if stage_assignment is not None:
        return stage_assignment
    return db.scalar(
        select(SceneAssignment.user_id).where(
            SceneAssignment.scene_id == work_step.scene_id,
            SceneAssignment.stage_key.is_(None),
        ).order_by(SceneAssignment.id).limit(1)
    )


def assert_can_execute_step(db: Session, work_step: SceneWorkStep, user: User) -> None:
    if user.role == "admin":
        return
    if user.role != "artist" or get_effective_assignee_id(db, work_step) != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the effective work step assignee can perform this action")


def assert_can_submit_stage(db: Session, scene: Scene, stage_key: str, user: User) -> None:
    if user.role == "admin":
        return
    if user.role != "artist":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only artists responsible for this stage can submit it for review")
    steps = list(
        db.scalars(
            select(SceneWorkStep).where(
                SceneWorkStep.scene_id == scene.id,
                SceneWorkStep.stage_key == stage_key,
                SceneWorkStep.status != "cancelled",
            )
        ).all()
    )
    if not any(get_effective_assignee_id(db, item) == user.id for item in steps):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only artists responsible for this stage can submit it for review")


def _lock_work_step(db: Session, work_step_id: int) -> SceneWorkStep:
    work_step = db.scalar(
        select(SceneWorkStep).where(SceneWorkStep.id == work_step_id).with_for_update()
    )
    if not work_step:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Work step not found")
    return work_step


def _stage_progress(db: Session, work_step: SceneWorkStep) -> StageProgress:
    stage_progress = db.get(StageProgress, work_step.stage_progress_id)
    if not stage_progress:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="StageProgress not found")
    return stage_progress


def _assert_stage_editable(stage_progress: StageProgress) -> None:
    if stage_progress.status in {"locked", "reviewing", "approved"}:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Work step action is not allowed while stage status is '{stage_progress.status}'",
        )


def sync_stage_status_after_step_action(
    db: Session,
    work_step: SceneWorkStep,
    action: str,
    operator_id: int,
) -> StageProgress:
    stage_progress = _stage_progress(db, work_step)
    if action in {"start", "submit", "withdraw"} and stage_progress.status in {"pending", "rejected"}:
        previous = stage_progress.status
        stage_progress.status = "in_progress"
        stage_progress.started_at = stage_progress.started_at or datetime.now(timezone.utc)
        record_work_step_event(
            db,
            work_step,
            operator_id,
            "stage.resume" if previous == "rejected" else "stage.start",
            from_status=previous,
            to_status="in_progress",
        )
    return stage_progress


def _ordered_active_steps(db: Session, work_step: SceneWorkStep) -> list[SceneWorkStep]:
    return list(
        db.scalars(
            select(SceneWorkStep).where(
                SceneWorkStep.scene_id == work_step.scene_id,
                SceneWorkStep.stage_key == work_step.stage_key,
                SceneWorkStep.status != "cancelled",
            ).order_by(SceneWorkStep.sort_order, SceneWorkStep.id)
        ).all()
    )


def refresh_step_availability(db: Session, work_step: SceneWorkStep, operator_id: int) -> None:
    stage_progress = _stage_progress(db, work_step)
    if stage_progress.status == "locked":
        return
    steps = _ordered_active_steps(db, work_step)
    for index, candidate in enumerate(steps):
        if candidate.status not in {"not_ready", "todo"}:
            continue
        required_predecessors = [item for item in steps[:index] if item.is_required]
        available = all(
            item.status in {"submitted", "done"} for item in required_predecessors
        )
        next_status = "todo" if available else "not_ready"
        if candidate.status != next_status:
            previous = candidate.status
            candidate.status = next_status
            record_work_step_event(
                db,
                candidate,
                operator_id,
                "step.unlock" if next_status == "todo" else "step.lock",
                from_status=previous,
                to_status=next_status,
            )


def activate_stage_work_steps(
    db: Session,
    scene: Scene,
    stage_progress: StageProgress,
    operator_id: int,
) -> list[SceneWorkStep]:
    ensure_default_for_stage(db, scene, stage_progress, operator_id)
    steps = list(
        db.scalars(
            select(SceneWorkStep).where(
                SceneWorkStep.stage_progress_id == stage_progress.id,
                SceneWorkStep.status != "cancelled",
            ).order_by(SceneWorkStep.sort_order, SceneWorkStep.id)
        ).all()
    )
    if steps:
        refresh_step_availability(db, steps[0], operator_id)
    return steps


def start_work_step(db: Session, work_step_id: int, user: User) -> SceneWorkStep:
    work_step = _lock_work_step(db, work_step_id)
    assert_can_execute_step(db, work_step, user)
    stage_progress = _stage_progress(db, work_step)
    _assert_stage_editable(stage_progress)
    if work_step.status not in {"todo", "needs_fix"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Cannot start work step from status '{work_step.status}'")
    previous = work_step.status
    work_step.status = "in_progress"
    work_step.started_at = work_step.started_at or datetime.now(timezone.utc)
    record_work_step_event(db, work_step, user.id, "step.start", from_status=previous, to_status="in_progress")
    sync_stage_status_after_step_action(db, work_step, "start", user.id)
    record_audit(
        db,
        user_id=user.id,
        action="work_step.start",
        target_type="scene_work_step",
        target_id=work_step.id,
        project_id=work_step.project_id,
        summary=f"开始步骤 {work_step.name}",
    )
    db.commit()
    db.refresh(work_step)
    return work_step


def submit_work_step(
    db: Session,
    work_step_id: int,
    user: User,
    asset_ids: list[int],
    note: str | None,
) -> StepSubmission:
    work_step = _lock_work_step(db, work_step_id)
    assert_can_execute_step(db, work_step, user)
    stage_progress = _stage_progress(db, work_step)
    _assert_stage_editable(stage_progress)
    if work_step.status not in {"in_progress", "needs_fix"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Cannot submit work step from status '{work_step.status}'")

    assets = list(db.scalars(select(Asset).where(Asset.id.in_(asset_ids)).with_for_update()).all())
    if len(assets) != len(asset_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more assets were not found")
    by_id = {asset.id: asset for asset in assets}
    for asset_id in asset_ids:
        asset = by_id[asset_id]
        if (
            asset.project_id != work_step.project_id
            or asset.scene_id != work_step.scene_id
            or asset.stage_key != work_step.stage_key
            or asset.scene_work_step_id != work_step.id
            or asset.asset_usage not in {"step_draft", "step_submission"}
            or asset.is_invalid
        ):
            raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=f"Asset {asset.id} is not a valid deliverable for this work step")

    version = (
        db.scalar(
            select(func.max(StepSubmission.version)).where(
                StepSubmission.scene_work_step_id == work_step.id
            )
        )
        or 0
    ) + 1
    submission = StepSubmission(
        project_id=work_step.project_id,
        scene_id=work_step.scene_id,
        scene_work_step_id=work_step.id,
        stage_progress_id=work_step.stage_progress_id,
        stage_key=work_step.stage_key,
        version=version,
        status="submitted",
        submitted_by=user.id,
        note=note,
    )
    db.add(submission)
    db.flush()
    for sort_order, asset_id in enumerate(asset_ids):
        db.add(StepSubmissionAsset(submission_id=submission.id, asset_id=asset_id, sort_order=sort_order))
        asset = by_id[asset_id]
        asset.asset_usage = "step_submission"
        asset.lifecycle_status = "submitted"

    previous = work_step.status
    work_step.status = "submitted"
    work_step.submitted_at = datetime.now(timezone.utc)
    record_work_step_event(
        db,
        work_step,
        user.id,
        "step.submit",
        from_status=previous,
        to_status="submitted",
        comment=note,
        payload_json={"submissionId": submission.id, "version": version, "assetIds": asset_ids},
    )
    sync_stage_status_after_step_action(db, work_step, "submit", user.id)
    refresh_step_availability(db, work_step, user.id)
    record_audit(
        db,
        user_id=user.id,
        action="work_step.submit",
        target_type="step_submission",
        target_id=submission.id,
        project_id=work_step.project_id,
        summary=f"提交步骤 {work_step.name} v{version}",
        payload_json={"workStepId": work_step.id, "assetIds": asset_ids},
    )
    notify_users_for_step(
        db, work_step,
        project_role_user_ids(db, work_step.project_id, {"admin", "director", "producer"}),
        "work_step_submitted", "步骤已有新提交",
        f"{work_step.stage_key} / {work_step.name} 已提交 v{version}",
        exclude_user_id=user.id,
    )
    db.commit()
    return get_submission(db, submission.id)


def get_submission(db: Session, submission_id: int) -> StepSubmission:
    submission = db.scalar(
        select(StepSubmission)
        .options(selectinload(StepSubmission.assets))
        .where(StepSubmission.id == submission_id)
    )
    if not submission:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Step submission not found")
    return submission


def list_submissions(db: Session, work_step_id: int) -> list[StepSubmission]:
    return list(
        db.scalars(
            select(StepSubmission)
            .options(selectinload(StepSubmission.assets))
            .where(StepSubmission.scene_work_step_id == work_step_id)
            .order_by(StepSubmission.version.desc())
        ).all()
    )


def withdraw_latest_submission(db: Session, work_step_id: int, user: User) -> StepSubmission:
    work_step = _lock_work_step(db, work_step_id)
    assert_can_execute_step(db, work_step, user)
    stage_progress = _stage_progress(db, work_step)
    if stage_progress.status in {"reviewing", "approved"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Submission cannot be withdrawn while the stage is reviewing or approved")
    submission = db.scalar(
        select(StepSubmission)
        .options(selectinload(StepSubmission.assets))
        .where(StepSubmission.scene_work_step_id == work_step.id)
        .order_by(StepSubmission.version.desc())
        .limit(1)
        .with_for_update()
    )
    if not submission or submission.status != "submitted" or work_step.status != "submitted":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Only the latest active submission can be withdrawn")
    if user.role != "admin" and submission.submitted_by != user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only the submitter can withdraw this submission")

    now = datetime.now(timezone.utc)
    submission.status = "withdrawn"
    submission.withdrawn_at = now
    for link in submission.assets:
        other_active = db.scalar(
            select(StepSubmissionAsset.id)
            .join(StepSubmission, StepSubmission.id == StepSubmissionAsset.submission_id)
            .where(
                StepSubmissionAsset.asset_id == link.asset_id,
                StepSubmission.id != submission.id,
                StepSubmission.status.in_({"submitted", "stage_accepted"}),
            ).limit(1)
        )
        if other_active is None:
            asset = db.get(Asset, link.asset_id)
            if asset:
                asset.lifecycle_status = "withdrawn"
    work_step.status = "in_progress"
    record_work_step_event(
        db,
        work_step,
        user.id,
        "step.withdraw",
        from_status="submitted",
        to_status="in_progress",
        payload_json={"submissionId": submission.id, "version": submission.version},
    )
    sync_stage_status_after_step_action(db, work_step, "withdraw", user.id)
    refresh_step_availability(db, work_step, user.id)
    record_audit(
        db,
        user_id=user.id,
        action="work_step.withdraw",
        target_type="step_submission",
        target_id=submission.id,
        project_id=work_step.project_id,
        summary=f"撤回步骤 {work_step.name} v{submission.version}",
    )
    db.commit()
    return get_submission(db, submission.id)


def cancel_work_step(db: Session, work_step_id: int, user: User) -> None:
    if user.role not in {"admin", "producer"}:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only producers or admins can cancel work steps")
    work_step = _lock_work_step(db, work_step_id)
    stage_progress = _stage_progress(db, work_step)
    if stage_progress.status in {"reviewing", "approved"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Work step cannot be cancelled while the stage is reviewing or approved")
    if work_step.status == "cancelled":
        return
    previous = work_step.status
    work_step.status = "cancelled"
    work_step.cancelled_at = datetime.now(timezone.utc)
    record_work_step_event(db, work_step, user.id, "step.cancel", from_status=previous, to_status="cancelled")
    refresh_step_availability(db, work_step, user.id)
    record_audit(
        db,
        user_id=user.id,
        action="work_step.cancel",
        target_type="scene_work_step",
        target_id=work_step.id,
        project_id=work_step.project_id,
        summary=f"停用步骤 {work_step.name}",
    )
    db.commit()


def ensure_stage_ready_for_review(db: Session, scene: Scene, stage_key: str, operator_id: int) -> list[SceneWorkStep]:
    stage_progress = db.scalar(
        select(StageProgress).where(StageProgress.scene_id == scene.id, StageProgress.stage_key == stage_key)
    )
    if not stage_progress:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="StageProgress not found")
    ensure_default_for_stage(db, scene, stage_progress, operator_id)
    steps = list(
        db.scalars(
            select(SceneWorkStep).where(
                SceneWorkStep.stage_progress_id == stage_progress.id,
                SceneWorkStep.status != "cancelled",
            ).order_by(SceneWorkStep.sort_order, SceneWorkStep.id)
        ).all()
    )
    incomplete = [item for item in steps if item.is_required and item.status not in {"submitted", "done"}]
    if incomplete:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "message": "Required work steps must be submitted before stage review",
                "workStepIds": [item.id for item in incomplete],
            },
        )
    return steps


def complete_submitted_steps_for_stage(
    db: Session,
    stage_progress: StageProgress,
    operator_id: int,
) -> None:
    now = datetime.now(timezone.utc)
    steps = list(
        db.scalars(
            select(SceneWorkStep).where(
                SceneWorkStep.stage_progress_id == stage_progress.id,
                SceneWorkStep.status == "submitted",
            )
        ).all()
    )
    for work_step in steps:
        work_step.status = "done"
        work_step.completed_at = now
        record_work_step_event(db, work_step, operator_id, "step.complete", from_status="submitted", to_status="done")
    submissions = list(
        db.scalars(
            select(StepSubmission).where(
                StepSubmission.stage_progress_id == stage_progress.id,
                StepSubmission.status == "submitted",
            )
        ).all()
    )
    for submission in submissions:
        submission.status = "stage_accepted"
        submission.reviewed_by = operator_id
        submission.reviewed_at = now


def reject_steps_for_stage(
    db: Session,
    stage_progress: StageProgress,
    operator_id: int,
    work_step_ids: list[int],
    reason: str | None,
    *,
    reject_all_submitted_steps: bool = False,
) -> list[SceneWorkStep]:
    stmt = select(SceneWorkStep).where(SceneWorkStep.stage_progress_id == stage_progress.id)
    if reject_all_submitted_steps:
        stmt = stmt.where(SceneWorkStep.status == "submitted")
    elif work_step_ids:
        stmt = stmt.where(SceneWorkStep.id.in_(work_step_ids))
    else:
        return []
    steps = list(db.scalars(stmt.with_for_update()).all())
    if not reject_all_submitted_steps and len(steps) != len(set(work_step_ids)):
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="One or more workStepIds do not belong to the stage")
    invalid = [item.id for item in steps if item.status not in {"submitted", "done"}]
    if invalid:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"message": "Only submitted or done work steps can be rejected", "workStepIds": invalid})
    now = datetime.now(timezone.utc)
    for work_step in steps:
        previous = work_step.status
        work_step.status = "needs_fix"
        work_step.completed_at = None
        record_work_step_event(
            db,
            work_step,
            operator_id,
            "step.needs_fix",
            from_status=previous,
            to_status="needs_fix",
            comment=reason,
        )
        submission = db.scalar(
            select(StepSubmission).where(
                StepSubmission.scene_work_step_id == work_step.id,
                StepSubmission.status.in_({"submitted", "stage_accepted"}),
            ).order_by(StepSubmission.version.desc()).limit(1)
        )
        if submission:
            submission.status = "stage_rejected"
            submission.reject_reason = reason
            submission.reviewed_by = operator_id
            submission.reviewed_at = now
        refresh_step_availability(db, work_step, operator_id)
    return steps


def complete_entry_steps(
    db: Session,
    scene: Scene,
    stage_progress: StageProgress,
    operator_id: int,
) -> None:
    now = datetime.now(timezone.utc)
    for work_step in activate_stage_work_steps(db, scene, stage_progress, operator_id):
        if work_step.status == "cancelled":
            continue
        previous = work_step.status
        work_step.status = "done"
        work_step.completed_at = now
        record_work_step_event(db, work_step, operator_id, "step.complete", from_status=previous, to_status="done", comment="Entry stage auto-approved")


def _validate_template_for_stage(
    db: Session,
    template_id: int,
    scene: Scene,
    stage_progress: StageProgress,
) -> WorkStepTemplate:
    template = db.scalar(
        select(WorkStepTemplate)
        .options(selectinload(WorkStepTemplate.items))
        .where(WorkStepTemplate.id == template_id)
    )
    if not template or not template.is_active:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Active work step template not found")
    if template.stage_key != stage_progress.stage_key:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Template stageKey does not match target stage")
    if template.scope == "project" and template.project_id != scene.project_id:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Project template does not belong to the target project")
    return template


def _template_item_values(item) -> dict:
    return {
        "name": item.name,
        "description": item.description,
        "sort_order": item.sort_order,
        "is_required": item.is_required,
        "allow_parallel": False,
        "metadata_json": dict(item.metadata_json) if item.metadata_json else None,
    }


def preview_template_application(
    db: Session,
    scene: Scene,
    stage_progress: StageProgress,
    template_id: int,
    mode: str,
) -> tuple[WorkStepTemplate, dict]:
    if stage_progress.status in {"reviewing", "approved"}:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Cannot apply a template while the stage is reviewing or approved")
    template = _validate_template_for_stage(db, template_id, scene, stage_progress)
    existing = list(
        db.scalars(
            select(SceneWorkStep)
            .where(SceneWorkStep.stage_progress_id == stage_progress.id)
            .order_by(SceneWorkStep.sort_order, SceneWorkStep.id)
        ).all()
    )
    existing_by_key = {item.step_key: item for item in existing}
    submission_step_ids = set(
        db.scalars(
            select(StepSubmission.scene_work_step_id)
            .where(StepSubmission.stage_progress_id == stage_progress.id)
            .distinct()
        ).all()
    )
    diff = {"add": [], "update": [], "restore": [], "keep": [], "cancel": []}
    template_keys = {item.step_key for item in template.items}
    for item in template.items:
        current = existing_by_key.get(item.step_key)
        summary = {"stepKey": item.step_key, "name": item.name, "workStepId": current.id if current else None}
        if current is None:
            diff["add"].append(summary)
        elif current.status == "cancelled":
            diff["restore"].append(summary)
        elif mode == "append" or current.id in submission_step_ids:
            diff["keep"].append(summary)
        else:
            values = _template_item_values(item)
            changes = {
                field: {"before": getattr(current, field), "after": value}
                for field, value in values.items()
                if getattr(current, field) != value
            }
            if changes:
                diff["update"].append({**summary, "changes": changes})
            else:
                diff["keep"].append(summary)
    if mode == "replace":
        for current in existing:
            if current.step_key not in template_keys and current.status != "cancelled":
                diff["cancel"].append({"stepKey": current.step_key, "name": current.name, "workStepId": current.id, "hasSubmissions": current.id in submission_step_ids})
    return template, {
        "sceneId": scene.id,
        "stageKey": stage_progress.stage_key,
        "stageProgressId": stage_progress.id,
        "templateId": template.id,
        "mode": mode,
        "diff": diff,
    }


def apply_template_to_stage(
    db: Session,
    scene: Scene,
    stage_progress: StageProgress,
    template_id: int,
    mode: str,
    operator_id: int,
) -> dict:
    template, preview = preview_template_application(db, scene, stage_progress, template_id, mode)
    existing = {
        item.step_key: item
        for item in db.scalars(select(SceneWorkStep).where(SceneWorkStep.stage_progress_id == stage_progress.id)).all()
    }
    changed_steps: list[SceneWorkStep] = []
    for diff_item in preview["diff"]["cancel"]:
        current = existing[diff_item["stepKey"]]
        previous = current.status
        current.status = "cancelled"
        current.cancelled_at = datetime.now(timezone.utc)
        record_work_step_event(db, current, operator_id, "step.cancel", from_status=previous, to_status="cancelled", payload_json={"templateId": template.id})
        changed_steps.append(current)
    item_by_key = {item.step_key: item for item in template.items}
    for category in ("add", "restore", "update"):
        for diff_item in preview["diff"][category]:
            source = item_by_key[diff_item["stepKey"]]
            current = existing.get(source.step_key)
            if current is None:
                current = SceneWorkStep(
                    project_id=scene.project_id,
                    scene_group_id=scene.scene_group_id,
                    scene_id=scene.id,
                    stage_progress_id=stage_progress.id,
                    stage_key=stage_progress.stage_key,
                    step_key=source.step_key,
                    original_name=source.name,
                    status="not_ready",
                    priority="normal",
                    created_by=operator_id,
                )
                db.add(current)
                existing[source.step_key] = current
            previous_status = current.status
            current.template_id = template.id
            current.template_item_id = source.id
            for field, value in _template_item_values(source).items():
                setattr(current, field, value)
            if category == "restore":
                current.status = "not_ready"
                current.cancelled_at = None
            db.flush()
            record_work_step_event(
                db,
                current,
                operator_id,
                "template.apply",
                from_status=previous_status,
                to_status=current.status,
                payload_json={"templateId": template.id, "mode": mode, "changeType": category},
            )
            changed_steps.append(current)
    active = next((item for item in existing.values() if item.status != "cancelled"), None)
    if active:
        refresh_step_availability(db, active, operator_id)
    record_audit(
        db,
        user_id=operator_id,
        action="work_step_template.apply",
        target_type="stage_progress",
        target_id=stage_progress.id,
        project_id=scene.project_id,
        summary=f"应用步骤模板 {template.name} 到 {scene.name}/{stage_progress.stage_key}",
        payload_json=preview,
    )
    return preview


def validate_assignee(db: Session, project_id: int, assignee_id: int | None) -> None:
    if assignee_id is None:
        return
    user = db.get(User, assignee_id)
    if not user or not user.is_active:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Assignee is not an active user")
    membership = db.scalar(
        select(UserProjectMembership.id).where(
            UserProjectMembership.project_id == project_id,
            UserProjectMembership.user_id == assignee_id,
        ).limit(1)
    )
    if membership is None:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Assignee is not a project member")


def batch_update_work_steps(
    db: Session,
    work_step_ids: list[int],
    changes: dict,
    operator_id: int,
) -> list[SceneWorkStep]:
    unique_ids = list(dict.fromkeys(work_step_ids))
    steps = list(
        db.scalars(
            select(SceneWorkStep).where(SceneWorkStep.id.in_(unique_ids)).with_for_update()
        ).all()
    )
    if len(steps) != len(unique_ids):
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="One or more work steps were not found")
    for project_id in {item.project_id for item in steps}:
        validate_assignee(db, project_id, changes.get("assignee_id")) if "assignee_id" in changes else None
    for work_step in steps:
        stage_progress = _stage_progress(db, work_step)
        if stage_progress.status in {"reviewing", "approved"}:
            raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=f"Work step {work_step.id} belongs to a locked stage")
        old_effective_assignee = get_effective_assignee_id(db, work_step)
        before = {field: getattr(work_step, field) for field in changes}
        for field, value in changes.items():
            setattr(work_step, field, value)
        action = "step.assign" if "assignee_id" in changes and before.get("assignee_id") != changes.get("assignee_id") else "step.update"
        record_work_step_event(
            db,
            work_step,
            operator_id,
            action,
            payload_json={"before": {key: value.isoformat() if isinstance(value, datetime) else value for key, value in before.items()}, "after": {key: value.isoformat() if isinstance(value, datetime) else value for key, value in changes.items()}},
        )
        record_audit(
            db,
            user_id=operator_id,
            action=f"work_step.{action.split('.')[-1]}",
            target_type="scene_work_step",
            target_id=work_step.id,
            project_id=work_step.project_id,
            summary=f"批量更新步骤 {work_step.name}",
            payload_json={
                "before": {key: value.isoformat() if isinstance(value, datetime) else value for key, value in before.items()},
                "after": {key: value.isoformat() if isinstance(value, datetime) else value for key, value in changes.items()},
            },
        )
        new_effective_assignee = get_effective_assignee_id(db, work_step)
        notify_step_schedule_change(
            db, work_step,
            old_assignee_id=old_effective_assignee,
            new_assignee_id=new_effective_assignee,
            assignee_changed="assignee_id" in changes and old_effective_assignee != new_effective_assignee,
            due_changed="due_at" in changes and before.get("due_at") != changes.get("due_at"),
            operator_id=operator_id,
        )
    return steps

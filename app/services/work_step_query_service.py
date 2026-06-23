from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domains.stage_templates import resolve_stage_template_steps
from app.models.project import Episode, Project, SceneAssignment, SceneGroup
from app.models.scene import Scene, StageProgress
from app.models.user import User
from app.models.work_step import SceneWorkStep, StepSubmission


def list_work_step_tasks(
    db: Session,
    *,
    project_id: int,
    episode_id: int | None = None,
    scene_group_id: int | None = None,
    scene_id: int | None = None,
    stage_key: str | None = None,
    assignee_id: int | None = None,
    statuses: list[str] | None = None,
    overdue_only: bool = False,
    blocked_only: bool = False,
    unassigned_only: bool = False,
    priority: str | None = None,
    keyword: str | None = None,
    include_cancelled: bool = False,
) -> dict:
    now = datetime.now(timezone.utc)
    stmt = (
        select(SceneWorkStep, Scene, SceneGroup, Episode, Project, StageProgress)
        .join(Scene, Scene.id == SceneWorkStep.scene_id)
        .join(SceneGroup, SceneGroup.id == Scene.scene_group_id)
        .outerjoin(Episode, Episode.id == SceneGroup.episode_id)
        .join(Project, Project.id == SceneWorkStep.project_id)
        .join(StageProgress, StageProgress.id == SceneWorkStep.stage_progress_id)
        .where(SceneWorkStep.project_id == project_id)
    )
    if episode_id is not None:
        stmt = stmt.where(SceneGroup.episode_id == episode_id)
    if scene_group_id is not None:
        stmt = stmt.where(SceneWorkStep.scene_group_id == scene_group_id)
    if scene_id is not None:
        stmt = stmt.where(SceneWorkStep.scene_id == scene_id)
    if stage_key:
        stmt = stmt.where(SceneWorkStep.stage_key == stage_key)
    if statuses:
        stmt = stmt.where(SceneWorkStep.status.in_(statuses))
    elif not include_cancelled:
        stmt = stmt.where(SceneWorkStep.status != "cancelled")
    if overdue_only:
        stmt = stmt.where(
            SceneWorkStep.is_required.is_(True),
            SceneWorkStep.due_at < now,
            SceneWorkStep.status.in_({"not_ready", "todo", "in_progress", "submitted", "needs_fix"}),
        )
    if blocked_only:
        stmt = stmt.where(or_(SceneWorkStep.blocked_reason.is_not(None), StageProgress.blocked_reason.is_not(None)))
    if priority:
        stmt = stmt.where(SceneWorkStep.priority == priority)
    if keyword:
        pattern = f"%{keyword.strip()}%"
        stmt = stmt.where(or_(Scene.name.ilike(pattern), SceneWorkStep.name.ilike(pattern)))
    rows = list(db.execute(stmt.order_by(SceneWorkStep.scene_id, SceneWorkStep.stage_key, SceneWorkStep.sort_order, SceneWorkStep.id)).all())
    if not rows:
        return {"items": [], "total": 0}

    scene_ids = {row[0].scene_id for row in rows}
    assignments = list(db.scalars(select(SceneAssignment).where(SceneAssignment.scene_id.in_(scene_ids))).all())
    stage_assignments = {}
    scene_assignments = {}
    for assignment in sorted(assignments, key=lambda item: item.id):
        if assignment.stage_key:
            stage_assignments.setdefault((assignment.scene_id, assignment.stage_key), assignment.user_id)
        else:
            scene_assignments.setdefault(assignment.scene_id, assignment.user_id)
    users = {item.id: item for item in db.scalars(select(User)).all()}
    work_step_ids = [row[0].id for row in rows]
    latest_by_step = {}
    for submission in db.scalars(
        select(StepSubmission)
        .where(StepSubmission.scene_work_step_id.in_(work_step_ids))
        .order_by(StepSubmission.scene_work_step_id, StepSubmission.version.desc())
    ).all():
        latest_by_step.setdefault(submission.scene_work_step_id, submission)

    template_cache = {}
    result = []
    for work_step, scene, group, episode, project, progress in rows:
        effective_id = work_step.assignee_id or progress.assignee_id or stage_assignments.get((scene.id, work_step.stage_key)) or scene_assignments.get(scene.id)
        if assignee_id is not None and effective_id != assignee_id:
            continue
        if unassigned_only and (not work_step.is_required or effective_id is not None):
            continue
        if scene.stage_template not in template_cache:
            template_cache[scene.stage_template] = {
                item["key"]: item.get("label") or item["key"]
                for item in resolve_stage_template_steps(db, scene.stage_template, project_id)
            }
        latest = latest_by_step.get(work_step.id)
        assignee = users.get(effective_id)
        result.append({
            "id": work_step.id,
            "projectId": project.id,
            "projectName": project.name,
            "episodeId": episode.id if episode else None,
            "episodeName": episode.name if episode else None,
            "sceneGroupId": group.id,
            "sceneGroupName": group.name,
            "sceneId": scene.id,
            "sceneName": scene.name,
            "stageProgressId": progress.id,
            "stageKey": work_step.stage_key,
            "stageLabel": template_cache[scene.stage_template].get(work_step.stage_key, work_step.stage_key),
            "stepKey": work_step.step_key,
            "name": work_step.name,
            "description": work_step.description,
            "status": work_step.status,
            "assigneeId": effective_id,
            "directAssigneeId": work_step.assignee_id,
            "assigneeName": assignee.display_name if assignee else None,
            "dueAt": work_step.due_at,
            "priority": work_step.priority,
            "isRequired": work_step.is_required,
            "allowParallel": work_step.allow_parallel,
            "sortOrder": work_step.sort_order,
            "latestSubmission": ({
                "id": latest.id,
                "version": latest.version,
                "status": latest.status,
                "submittedBy": latest.submitted_by,
                "createdAt": latest.created_at,
            } if latest else None),
            "inputAssetCount": 0,
            "isOverdue": bool(work_step.is_required and work_step.due_at and work_step.due_at < now and work_step.status not in {"done", "cancelled"}),
            "blockedReason": work_step.blocked_reason or progress.blocked_reason,
            "note": work_step.note,
            "createdAt": work_step.created_at,
            "updatedAt": work_step.updated_at,
        })
    return {"items": result, "total": len(result)}

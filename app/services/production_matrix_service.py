from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.domains.stage_templates import resolve_stage_template_steps
from app.models.asset import Asset
from app.models.project import Project, SceneAssignment, SceneGroup
from app.models.scene import Scene, StageProgress
from app.models.user import User
from app.models.work_step import SceneWorkStep, StepSubmission, StepSubmissionAsset


OPEN_STEP_STATUSES = {"not_ready", "todo", "in_progress", "submitted", "needs_fix"}


def _timestamp(value) -> float:
    return value.timestamp() if value else 0.0


def _is_overdue(step: SceneWorkStep, now: datetime) -> bool:
    return bool(step.is_required and step.due_at and step.due_at < now and step.status in OPEN_STEP_STATUSES)


def _overall_status(cells: dict[str, dict]) -> str:
    statuses = [cell["stageStatus"] for cell in cells.values()]
    for candidate in ("rejected", "reviewing", "in_progress", "pending", "locked"):
        if candidate in statuses:
            return candidate
    return "approved" if statuses else "locked"


def build_production_matrix(
    db: Session,
    *,
    project_id: int,
    episode_id: int | None = None,
    scene_group_id: int | None = None,
    stage_key: str | None = None,
    assignee_id: int | None = None,
    work_step_statuses: list[str] | None = None,
    overdue_only: bool = False,
    blocked_only: bool = False,
    unassigned_only: bool = False,
    priority: str | None = None,
    keyword: str | None = None,
) -> dict:
    project = db.get(Project, project_id)
    if not project:
        return {}
    now = datetime.now(timezone.utc)
    groups = list(
        db.scalars(
            select(SceneGroup)
            .where(SceneGroup.project_id == project_id)
            .order_by(SceneGroup.sort_order, SceneGroup.id)
        ).all()
    )
    if episode_id is not None:
        groups = [group for group in groups if group.episode_id == episode_id]
    if scene_group_id is not None:
        groups = [group for group in groups if group.id == scene_group_id]
    group_ids = {group.id for group in groups}
    if not group_ids:
        return _empty_matrix(project_id, episode_id)

    scenes = list(
        db.scalars(
            select(Scene)
            .where(Scene.project_id == project_id, Scene.scene_group_id.in_(group_ids))
            .order_by(Scene.scene_group_id, Scene.sort_order, Scene.id)
        ).all()
    )
    scene_ids = [scene.id for scene in scenes]
    if not scene_ids:
        return _empty_matrix(project_id, episode_id, groups)

    progresses = list(db.scalars(select(StageProgress).where(StageProgress.scene_id.in_(scene_ids))).all())
    steps = list(
        db.scalars(
            select(SceneWorkStep)
            .where(SceneWorkStep.scene_id.in_(scene_ids))
            .order_by(SceneWorkStep.scene_id, SceneWorkStep.stage_key, SceneWorkStep.sort_order, SceneWorkStep.id)
        ).all()
    )
    assignments = list(db.scalars(select(SceneAssignment).where(SceneAssignment.scene_id.in_(scene_ids))).all())
    users = {user.id: user for user in db.scalars(select(User)).all()}

    progress_by_scene_stage = {(item.scene_id, item.stage_key): item for item in progresses}
    steps_by_scene_stage: dict[tuple[int, str], list[SceneWorkStep]] = defaultdict(list)
    steps_by_scene: dict[int, list[SceneWorkStep]] = defaultdict(list)
    for item in steps:
        steps_by_scene_stage[(item.scene_id, item.stage_key)].append(item)
        steps_by_scene[item.scene_id].append(item)
    stage_assignments: dict[tuple[int, str], int] = {}
    scene_assignments: dict[int, int] = {}
    for assignment in sorted(assignments, key=lambda item: item.id):
        if assignment.stage_key:
            stage_assignments.setdefault((assignment.scene_id, assignment.stage_key), assignment.user_id)
        else:
            scene_assignments.setdefault(assignment.scene_id, assignment.user_id)

    def effective_assignee(step: SceneWorkStep, progress: StageProgress | None) -> int | None:
        return (
            step.assignee_id
            or (progress.assignee_id if progress else None)
            or stage_assignments.get((step.scene_id, step.stage_key))
            or scene_assignments.get(step.scene_id)
        )

    normalized_keyword = (keyword or "").strip().lower()
    status_filter = set(work_step_statuses or [])
    matching_scene_ids: set[int] = set()
    filters_active = any((stage_key, assignee_id, status_filter, overdue_only, blocked_only, unassigned_only, priority, normalized_keyword))
    for scene in scenes:
        scene_matches = False
        for step in steps_by_scene.get(scene.id, []):
            progress = progress_by_scene_stage.get((step.scene_id, step.stage_key))
            effective_id = effective_assignee(step, progress)
            if stage_key and step.stage_key != stage_key:
                continue
            if assignee_id is not None and effective_id != assignee_id:
                continue
            if status_filter and step.status not in status_filter:
                continue
            if overdue_only and not _is_overdue(step, now):
                continue
            if blocked_only and not (step.blocked_reason or (progress and progress.blocked_reason)):
                continue
            if unassigned_only and (not step.is_required or effective_id is not None):
                continue
            if priority and step.priority != priority:
                continue
            if normalized_keyword and normalized_keyword not in scene.name.lower() and normalized_keyword not in step.name.lower():
                continue
            scene_matches = True
            break
        if scene_matches or not filters_active:
            matching_scene_ids.add(scene.id)
    scenes = [scene for scene in scenes if scene.id in matching_scene_ids]
    scene_ids = [scene.id for scene in scenes]
    if not scenes:
        return _empty_matrix(project_id, episode_id, groups)

    submissions = list(
        db.scalars(
            select(StepSubmission)
            .where(StepSubmission.scene_id.in_(scene_ids), StepSubmission.status != "withdrawn")
            .order_by(StepSubmission.created_at.desc(), StepSubmission.id.desc())
        ).all()
    )
    submission_ids = [item.id for item in submissions]
    links = list(
        db.scalars(select(StepSubmissionAsset).where(StepSubmissionAsset.submission_id.in_(submission_ids))).all()
    ) if submission_ids else []
    assets = list(
        db.scalars(
            select(Asset)
            .where(Asset.project_id == project_id, Asset.scene_id.in_(scene_ids))
            .order_by(Asset.created_at.desc(), Asset.id.desc())
        ).all()
    )
    assets_by_id = {asset.id: asset for asset in assets}
    links_by_submission: dict[int, list[StepSubmissionAsset]] = defaultdict(list)
    for link in sorted(links, key=lambda item: (item.sort_order, item.id)):
        links_by_submission[link.submission_id].append(link)
    submission_by_stage: dict[tuple[int, str], StepSubmission] = {}
    for submission in submissions:
        submission_by_stage.setdefault((submission.scene_id, submission.stage_key), submission)
    assets_by_stage: dict[tuple[int, str], list[Asset]] = defaultdict(list)
    for asset in assets:
        assets_by_stage[(asset.scene_id, asset.stage_key)].append(asset)

    template_stage_cache: dict[str, list[dict]] = {}
    ordered_stage_keys: list[str] = []
    stage_meta: dict[str, dict] = {}
    for scene in scenes:
        if scene.stage_template not in template_stage_cache:
            template_stage_cache[scene.stage_template] = resolve_stage_template_steps(db, scene.stage_template, project_id)
        for index, item in enumerate(template_stage_cache[scene.stage_template]):
            key = item["key"]
            stage_meta.setdefault(key, {"key": key, "label": item.get("label") or key, "sortOrder": (index + 1) * 10, "color": None})
            if key not in ordered_stage_keys:
                ordered_stage_keys.append(key)
    if stage_key:
        ordered_stage_keys = [key for key in ordered_stage_keys if key == stage_key]

    scene_payloads = []
    summary = {"sceneCount": len(scenes), "stageCellCount": 0, "overdueCellCount": 0, "unassignedCellCount": 0, "blockedCellCount": 0, "reviewingCellCount": 0}
    for scene in scenes:
        cells: dict[str, dict] = {}
        blocked_flags: set[str] = set()
        for key in ordered_stage_keys:
            progress = progress_by_scene_stage.get((scene.id, key))
            if not progress:
                continue
            stage_steps = steps_by_scene_stage.get((scene.id, key), [])
            active_steps = [item for item in stage_steps if item.status != "cancelled"]
            required_steps = [item for item in active_steps if item.is_required]
            effective_ids = {item.id: effective_assignee(item, progress) for item in active_steps}
            overdue_steps = [item for item in required_steps if _is_overdue(item, now)]
            unassigned_count = sum(1 for item in required_steps if effective_ids[item.id] is None)

            def current_sort(item: SceneWorkStep):
                overdue = _is_overdue(item, now)
                if item.status == "needs_fix": rank = 0
                elif overdue: rank = 1
                elif item.status == "in_progress": rank = 2
                elif item.status == "todo": rank = 3
                elif item.status == "submitted": rank = 4
                elif item.status == "done": rank = 5
                else: rank = 6
                secondary = _timestamp(item.due_at) if item.status == "todo" and item.due_at else -_timestamp(item.submitted_at or item.completed_at)
                return rank, secondary, item.sort_order, item.id

            current = min(active_steps, key=current_sort) if active_steps else None
            current_assignee_id = effective_ids.get(current.id) if current else None
            current_user = users.get(current_assignee_id)
            assignee_names = []
            for assignee in dict.fromkeys(value for value in effective_ids.values() if value is not None):
                if users.get(assignee):
                    assignee_names.append(users[assignee].display_name)
            latest_submission = submission_by_stage.get((scene.id, key))
            latest_links = links_by_submission.get(latest_submission.id, []) if latest_submission else []
            latest_asset = None
            for link in latest_links:
                candidate = assets_by_id.get(link.asset_id)
                if candidate and not candidate.is_invalid:
                    latest_asset = candidate
                    break
            if latest_asset is None:
                latest_asset = next((item for item in assets_by_stage.get((scene.id, key), []) if not item.is_invalid), None)
            has_blocked = bool(progress.blocked_reason or any(item.blocked_reason for item in active_steps))
            has_needs_fix = any(item.status == "needs_fix" for item in active_steps)
            has_invalid_asset = any(item.is_invalid for item in assets_by_stage.get((scene.id, key), []))
            flags = {
                "isOverdue": bool(overdue_steps),
                "hasUnassigned": unassigned_count > 0,
                "hasBlocked": has_blocked,
                "hasNeedsFix": has_needs_fix,
                "missingInput": False,
                "hasInvalidAsset": has_invalid_asset,
            }
            if flags["isOverdue"]: blocked_flags.add("overdue")
            if flags["hasUnassigned"]: blocked_flags.add("unassigned")
            if flags["hasBlocked"]: blocked_flags.add("blocked")
            if flags["hasNeedsFix"]: blocked_flags.add("needs_fix")
            cell = {
                "stageProgressId": progress.id,
                "stageKey": key,
                "stageLabel": stage_meta.get(key, {}).get("label", key),
                "stageStatus": progress.status,
                "canSubmitStage": all(item.status in {"submitted", "done"} for item in required_steps) and progress.status in {"in_progress", "rejected"},
                "requiredStepCount": len(required_steps),
                "doneStepCount": sum(item.status == "done" for item in active_steps),
                "submittedStepCount": sum(item.status == "submitted" for item in active_steps),
                "inProgressStepCount": sum(item.status == "in_progress" for item in active_steps),
                "needsFixStepCount": sum(item.status == "needs_fix" for item in active_steps),
                "cancelledStepCount": sum(item.status == "cancelled" for item in stage_steps),
                "currentStep": ({
                    "id": current.id,
                    "name": current.name,
                    "status": current.status,
                    "assigneeId": current_assignee_id,
                    "assigneeName": current_user.display_name if current_user else None,
                    "dueAt": current.due_at,
                    "priority": current.priority,
                    "isOverdue": _is_overdue(current, now),
                } if current else None),
                "assigneeSummary": {
                    "primaryAssigneeId": current_assignee_id or progress.assignee_id,
                    "primaryAssigneeName": (users.get(current_assignee_id or progress.assignee_id).display_name if users.get(current_assignee_id or progress.assignee_id) else None),
                    "assigneeNames": assignee_names,
                    "unassignedCount": unassigned_count,
                },
                "latestSubmission": ({
                    "id": latest_submission.id,
                    "workStepId": latest_submission.scene_work_step_id,
                    "workStepName": next((item.name for item in active_steps if item.id == latest_submission.scene_work_step_id), None),
                    "version": latest_submission.version,
                    "status": latest_submission.status,
                    "submittedBy": latest_submission.submitted_by,
                    "submittedByName": users.get(latest_submission.submitted_by).display_name if users.get(latest_submission.submitted_by) else None,
                    "createdAt": latest_submission.created_at,
                    "assetCount": len(latest_links),
                } if latest_submission else None),
                "latestAsset": ({
                    "id": latest_asset.id,
                    "mediaType": latest_asset.media_type,
                    "thumbnailUrl": latest_asset.thumbnail_url,
                    "url": latest_asset.public_url,
                    "originalName": latest_asset.original_name,
                } if latest_asset else None),
                "flags": flags,
                "blockedReason": progress.blocked_reason or next((item.blocked_reason for item in active_steps if item.blocked_reason), None),
                "productionNote": progress.production_note,
            }
            cells[key] = cell
            summary["stageCellCount"] += 1
            summary["overdueCellCount"] += int(flags["isOverdue"])
            summary["unassignedCellCount"] += int(flags["hasUnassigned"])
            summary["blockedCellCount"] += int(flags["hasBlocked"])
            summary["reviewingCellCount"] += int(progress.status == "reviewing")
        scene_payloads.append({
            "id": scene.id,
            "name": scene.name,
            "sceneGroupId": scene.scene_group_id,
            "level": scene.level,
            "frameCount": scene.frame_count,
            "durationSeconds": float(scene.duration_seconds) if scene.duration_seconds is not None else None,
            "sortOrder": scene.sort_order,
            "stageTemplate": scene.stage_template,
            "overallStatus": _overall_status(cells),
            "blockedFlags": sorted(blocked_flags),
            "stageCells": cells,
        })

    included_group_ids = {scene.scene_group_id for scene in scenes}
    return {
        "projectId": project_id,
        "episodeId": episode_id,
        "generatedAt": now,
        "stages": [stage_meta[key] for key in ordered_stage_keys if key in stage_meta],
        "sceneGroups": [{
            "id": group.id,
            "name": group.name,
            "episodeId": group.episode_id,
            "sortOrder": group.sort_order,
            "sceneIds": [scene.id for scene in scenes if scene.scene_group_id == group.id],
        } for group in groups if group.id in included_group_ids],
        "scenes": scene_payloads,
        "summary": summary,
    }


def _empty_matrix(project_id: int, episode_id: int | None, groups: list[SceneGroup] | None = None) -> dict:
    return {
        "projectId": project_id,
        "episodeId": episode_id,
        "generatedAt": datetime.now(timezone.utc),
        "stages": [],
        "sceneGroups": [{"id": item.id, "name": item.name, "episodeId": item.episode_id, "sortOrder": item.sort_order, "sceneIds": []} for item in (groups or [])],
        "scenes": [],
        "summary": {"sceneCount": 0, "stageCellCount": 0, "overdueCellCount": 0, "unassignedCellCount": 0, "blockedCellCount": 0, "reviewingCellCount": 0},
    }

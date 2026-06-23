from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.domains.stage_templates import resolve_stage_template_steps
from app.models.asset import Asset
from app.models.project import Episode, SceneAssignment, SceneGroup
from app.models.scene import Scene, StageProgress
from app.models.user import User
from app.models.workflow import ReviewRecord
from app.models.work_step import SceneWorkStep, StepSubmission, StepSubmissionAsset


UNFINISHED = {"not_ready", "todo", "in_progress", "submitted", "needs_fix"}


def get_project_step_progress(db: Session, project_id: int) -> dict:
    now = datetime.now(timezone.utc)
    scenes = list(db.scalars(select(Scene).where(Scene.project_id == project_id).order_by(Scene.sort_order, Scene.id)).all())
    scene_ids = [item.id for item in scenes]
    scenes_by_id = {item.id: item for item in scenes}
    groups = {item.id: item for item in db.scalars(select(SceneGroup).where(SceneGroup.project_id == project_id)).all()}
    episode_ids = {item.episode_id for item in groups.values() if item.episode_id}
    episodes = {item.id: item for item in db.scalars(select(Episode).where(Episode.id.in_(episode_ids or {-1}))).all()}
    progresses = list(db.scalars(select(StageProgress).where(StageProgress.scene_id.in_(scene_ids or [-1]))).all())
    steps = list(db.scalars(select(SceneWorkStep).where(
        SceneWorkStep.project_id == project_id, SceneWorkStep.status != "cancelled"
    ).order_by(SceneWorkStep.scene_id, SceneWorkStep.stage_key, SceneWorkStep.sort_order, SceneWorkStep.id)).all())
    progress_by_id = {item.id: item for item in progresses}
    progress_by_scene_stage = {(item.scene_id, item.stage_key): item for item in progresses}

    assignments = list(db.scalars(select(SceneAssignment).where(SceneAssignment.scene_id.in_(scene_ids or [-1]))).all())
    stage_assignees, scene_assignees = {}, {}
    for item in sorted(assignments, key=lambda value: value.id):
        if item.stage_key:
            stage_assignees.setdefault((item.scene_id, item.stage_key), item.user_id)
        else:
            scene_assignees.setdefault(item.scene_id, item.user_id)

    effective_assignees = {}
    for step in steps:
        progress = progress_by_id[step.stage_progress_id]
        effective_assignees[step.id] = (
            step.assignee_id or progress.assignee_id
            or stage_assignees.get((step.scene_id, step.stage_key))
            or scene_assignees.get(step.scene_id)
        )
    user_ids = {item for item in effective_assignees.values() if item}
    users = {item.id: item for item in db.scalars(select(User).where(User.id.in_(user_ids or {-1}))).all()}

    stage_defs_by_scene, stage_labels, stage_order = {}, {}, []
    template_cache = {}
    for scene in scenes:
        cache_key = (scene.stage_template, scene.project_id)
        if cache_key not in template_cache:
            template_cache[cache_key] = resolve_stage_template_steps(db, scene.stage_template, scene.project_id)
        definitions = template_cache[cache_key]
        stage_defs_by_scene[scene.id] = definitions
        for definition in definitions:
            stage_labels[definition["key"]] = definition.get("label") or definition["key"]
            if definition["key"] not in stage_order:
                stage_order.append(definition["key"])

    completed_scene_ids = set()
    for scene in scenes:
        definitions = stage_defs_by_scene.get(scene.id) or []
        if definitions and progress_by_scene_stage.get((scene.id, definitions[-1]["key"])) and progress_by_scene_stage[(scene.id, definitions[-1]["key"])].status == "approved":
            completed_scene_ids.add(scene.id)
    in_progress_scene_ids = {
        item.scene_id for item in progresses if item.status in {"pending", "in_progress", "reviewing", "rejected"}
    } - completed_scene_ids

    stage_counts = defaultdict(Counter)
    for progress in progresses:
        stage_counts[progress.stage_key][progress.status] += 1
    stages = []
    for key in stage_order:
        counts = stage_counts[key]
        total = sum(counts.values())
        stages.append({
            "key": key, "label": stage_labels.get(key, key), "total": total,
            "approved": counts["approved"], "completionRate": round(counts["approved"] * 100 / total, 1) if total else 0,
            "statuses": dict(counts),
        })

    step_status_counts = Counter(item.status for item in steps)
    status_order = ["not_ready", "todo", "in_progress", "submitted", "needs_fix", "done"]
    step_statuses = [{"status": key, "count": step_status_counts[key]} for key in status_order if step_status_counts[key]]

    latest_submission_asset_steps = set(db.scalars(
        select(StepSubmission.scene_work_step_id)
        .join(StepSubmissionAsset, StepSubmissionAsset.submission_id == StepSubmission.id)
        .join(Asset, Asset.id == StepSubmissionAsset.asset_id)
        .where(
            StepSubmission.project_id == project_id,
            StepSubmission.status.in_({"submitted", "stage_accepted"}),
            Asset.is_invalid.is_(False),
        ).distinct()
    ).all())
    valid_assets = list(db.scalars(select(Asset).where(
        Asset.project_id == project_id, Asset.scene_id.in_(scene_ids or [-1]),
        Asset.is_invalid.is_(False), Asset.lifecycle_status != "invalid",
    )).all())
    asset_stage_pairs = {(item.scene_id, item.stage_key) for item in valid_assets}

    steps_by_scene_stage = defaultdict(list)
    for step in steps:
        steps_by_scene_stage[(step.scene_id, step.stage_key)].append(step)

    blockers = []
    overdue_scene_ids = set()
    workload = defaultdict(lambda: Counter(total=0, active=0, overdue=0, needsFix=0, submitted=0, done=0))
    for step in steps:
        effective_id = effective_assignees[step.id]
        stage_is_unlocked = progress_by_id[step.stage_progress_id].status != "locked"
        is_actionable = stage_is_unlocked and step.status in UNFINISHED
        is_overdue = bool(step.is_required and step.due_at and step.due_at < now and step.status in UNFINISHED)
        reasons, types = [], []
        if is_overdue:
            reasons.append("已超过截止时间"); types.append("overdue"); overdue_scene_ids.add(step.scene_id)
        if step.is_required and effective_id is None and is_actionable:
            reasons.append("必做步骤未分配负责人"); types.append("unassigned")
        if step.status == "needs_fix":
            reasons.append("导演驳回后待修改"); types.append("needs_fix")
        blocked_reason = step.blocked_reason or progress_by_id[step.stage_progress_id].blocked_reason
        if blocked_reason:
            reasons.append(blocked_reason); types.append("blocked")

        ordered = steps_by_scene_stage[(step.scene_id, step.stage_key)]
        predecessors = [item for item in ordered if item.is_required and (item.sort_order, item.id) < (step.sort_order, step.id)]
        missing = []
        if predecessors and any(item.id not in latest_submission_asset_steps for item in predecessors):
            missing.append("缺前置步骤提交物")
        definitions = stage_defs_by_scene.get(step.scene_id) or []
        keys = [item["key"] for item in definitions]
        if step.stage_key in keys and keys.index(step.stage_key) > 0:
            upstream_keys = keys[:keys.index(step.stage_key)]
            approved_upstream = {
                key for key in upstream_keys
                if progress_by_scene_stage.get((step.scene_id, key)) and progress_by_scene_stage[(step.scene_id, key)].status == "approved"
            }
            if not any((step.scene_id, key) in asset_stage_pairs for key in approved_upstream):
                missing.append("缺上游阶段文件")
        if missing and is_actionable:
            reasons.extend(missing); types.append("missing_input")

        if effective_id:
            row = workload[effective_id]
            row["total"] += 1
            if is_actionable: row["active"] += 1
            if is_overdue: row["overdue"] += 1
            if step.status == "needs_fix": row["needsFix"] += 1
            if step.status == "submitted": row["submitted"] += 1
            if step.status == "done": row["done"] += 1
        if reasons:
            scene, group = scenes_by_id[step.scene_id], groups[step.scene_group_id]
            episode = episodes.get(group.episode_id)
            blockers.append({
                "workStepId": step.id, "projectId": project_id, "sceneId": step.scene_id,
                "sceneName": scene.name, "sceneGroupId": group.id, "sceneGroupName": group.name,
                "episodeId": episode.id if episode else None, "episodeName": episode.name if episode else None,
                "stageKey": step.stage_key, "stageLabel": stage_labels.get(step.stage_key, step.stage_key),
                "workStepName": step.name, "status": step.status, "priority": step.priority,
                "assigneeId": effective_id, "assigneeName": users[effective_id].display_name if effective_id in users else None,
                "dueAt": step.due_at, "types": list(dict.fromkeys(types)), "reasons": list(dict.fromkeys(reasons)),
            })
    blockers.sort(key=lambda item: (0 if "overdue" in item["types"] else 1, item["dueAt"] or datetime.max.replace(tzinfo=timezone.utc), item["sceneId"], item["workStepId"]))

    workloads = [{"userId": user_id, "userName": users[user_id].display_name, **dict(counts)} for user_id, counts in workload.items()]
    workloads.sort(key=lambda item: (-item["active"], -item["overdue"], item["userName"]))
    rejection_count = db.scalar(select(func.count(ReviewRecord.id)).where(
        ReviewRecord.project_id == project_id, ReviewRecord.action == "reject"
    )) or 0
    return {
        "projectId": project_id,
        "summary": {
            "totalScenes": len(scenes), "completedScenes": len(completed_scene_ids),
            "inProgressScenes": len(in_progress_scene_ids), "overdueScenes": len(overdue_scene_ids),
            "rejectionCount": rejection_count, "totalWorkSteps": len(steps), "blockerCount": len(blockers),
        },
        "stages": stages, "stepStatuses": step_statuses, "workloads": workloads, "blockers": blockers,
    }

from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.domains.stage_templates import resolve_stage_template_steps
from app.models.annotation import Annotation, AnnotationAttachment
from app.models.asset import Asset
from app.models.project import Episode, Project, SceneAssignment, SceneGroup
from app.models.scene import Scene, StageProgress
from app.models.user import User
from app.models.work_step import SceneWorkStep, StepSubmission, StepSubmissionAsset


def list_work_step_tasks(
    db: Session,
    *,
    project_id: int | None,
    project_ids: list[int] | None = None,
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
    )
    if project_id is not None:
        stmt = stmt.where(SceneWorkStep.project_id == project_id)
    elif project_ids is not None:
        if not project_ids:
            return {"items": [], "total": 0}
        stmt = stmt.where(SceneWorkStep.project_id.in_(project_ids))
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
                for item in resolve_stage_template_steps(db, scene.stage_template, project.id)
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
    if result:
        counts = input_asset_counts(db, [item["id"] for item in result])
        for item in result:
            summary = counts.get(item["id"], {"count": 0, "missing": False, "reasons": []})
            item["inputAssetCount"] = summary["count"]
            item["missingInput"] = summary["missing"]
            item["missingInputReasons"] = summary["reasons"]
    return {"items": result, "total": len(result)}


def _asset_dict(asset: Asset, *, source_type: str, source_label: str) -> dict:
    return {
        "id": asset.id,
        "sourceType": source_type,
        "sourceLabel": source_label,
        "projectId": asset.project_id,
        "sceneGroupId": asset.scene_group_id,
        "sceneId": asset.scene_id,
        "stageKey": asset.stage_key,
        "sceneWorkStepId": asset.scene_work_step_id,
        "assetUsage": asset.asset_usage,
        "lifecycleStatus": asset.lifecycle_status,
        "mediaType": asset.media_type,
        "originalName": asset.original_name,
        "url": asset.public_url,
        "thumbnailUrl": asset.thumbnail_url,
        "version": asset.version,
        "note": asset.note,
        "createdAt": asset.created_at,
    }


def _input_context(db: Session, work_step: SceneWorkStep) -> dict:
    scene = db.get(Scene, work_step.scene_id)
    progress = db.get(StageProgress, work_step.stage_progress_id)
    stage_defs = resolve_stage_template_steps(db, scene.stage_template, scene.project_id)
    stage_keys = [item["key"] for item in stage_defs]
    try:
        stage_index = stage_keys.index(work_step.stage_key)
    except ValueError:
        stage_index = 0
    upstream_keys = stage_keys[:stage_index]

    stage_steps = list(db.scalars(
        select(SceneWorkStep).where(
            SceneWorkStep.scene_id == work_step.scene_id,
            SceneWorkStep.stage_key == work_step.stage_key,
            SceneWorkStep.status != "cancelled",
        ).order_by(SceneWorkStep.sort_order, SceneWorkStep.id)
    ).all())
    predecessors = [item for item in stage_steps if item.is_required and (item.sort_order, item.id) < (work_step.sort_order, work_step.id)]

    group_assets = list(db.scalars(select(Asset).where(
        Asset.project_id == work_step.project_id,
        Asset.scene_group_id == work_step.scene_group_id,
        Asset.scene_id.is_(None),
        Asset.is_invalid.is_(False),
        Asset.lifecycle_status != "invalid",
    ).order_by(Asset.id.desc())).all())
    supplemental_assets = list(db.scalars(select(Asset).where(
        Asset.scene_id == work_step.scene_id,
        Asset.stage_key == work_step.stage_key,
        Asset.scene_work_step_id.is_(None),
        Asset.asset_usage.in_({"reference", "stage_asset"}),
        Asset.is_invalid.is_(False),
        Asset.lifecycle_status != "invalid",
    ).order_by(Asset.id.desc())).all())

    approved_keys = set(db.scalars(select(StageProgress.stage_key).where(
        StageProgress.scene_id == work_step.scene_id,
        StageProgress.stage_key.in_(upstream_keys or ["__none__"]),
        StageProgress.status == "approved",
    )).all())
    upstream_assets = list(db.scalars(select(Asset).where(
        Asset.scene_id == work_step.scene_id,
        Asset.stage_key.in_(approved_keys or {"__none__"}),
        Asset.is_invalid.is_(False),
        Asset.lifecycle_status != "invalid",
    ).order_by(Asset.id.desc())).all())

    predecessor_ids = [item.id for item in predecessors]
    predecessor_rows = list(db.execute(
        select(Asset, SceneWorkStep)
        .join(StepSubmissionAsset, StepSubmissionAsset.asset_id == Asset.id)
        .join(StepSubmission, StepSubmission.id == StepSubmissionAsset.submission_id)
        .join(SceneWorkStep, SceneWorkStep.id == StepSubmission.scene_work_step_id)
        .where(
            StepSubmission.scene_work_step_id.in_(predecessor_ids or [-1]),
            StepSubmission.status.in_({"submitted", "stage_accepted"}),
            Asset.is_invalid.is_(False),
        )
        .order_by(SceneWorkStep.sort_order, StepSubmission.version.desc(), StepSubmissionAsset.sort_order)
    ).all())

    groups = [
        {"key": "scene_group_reference", "label": "镜头组参考素材", "assets": [_asset_dict(a, source_type="scene_group_reference", source_label="镜头组参考素材") for a in group_assets]},
        {"key": "stage_supplement", "label": "当前阶段补充资料", "assets": [_asset_dict(a, source_type="stage_supplement", source_label="当前阶段补充资料") for a in supplemental_assets]},
        {"key": "upstream_stage", "label": "上游阶段通过文件", "assets": [_asset_dict(a, source_type="upstream_stage", source_label=f"上游阶段 · {a.stage_key}") for a in upstream_assets]},
        {"key": "previous_work_step", "label": "前置步骤提交物", "assets": [_asset_dict(a, source_type="previous_work_step", source_label=f"前置步骤 · {s.name}") for a, s in predecessor_rows]},
    ]
    missing_reasons = []
    submitted_predecessor_ids = {step.id for _, step in predecessor_rows}
    if predecessors and any(item.id not in submitted_predecessor_ids for item in predecessors):
        missing_reasons.append("缺前置步骤提交物")
    if stage_index > 0 and not upstream_assets:
        missing_reasons.append("缺上游阶段文件")

    own_submission_rows = list(db.execute(
        select(StepSubmission, Asset)
        .join(StepSubmissionAsset, StepSubmissionAsset.submission_id == StepSubmission.id)
        .join(Asset, Asset.id == StepSubmissionAsset.asset_id)
        .where(StepSubmission.scene_work_step_id == work_step.id)
        .order_by(StepSubmission.version.desc(), StepSubmissionAsset.sort_order)
    ).all())
    submission_assets: dict[int, list[dict]] = defaultdict(list)
    submission_models = {}
    for submission, asset in own_submission_rows:
        submission_models[submission.id] = submission
        submission_assets[submission.id].append(_asset_dict(asset, source_type="submission", source_label=f"提交 v{submission.version}"))
    submissions = [{
        "id": item.id, "version": item.version, "status": item.status, "note": item.note,
        "rejectReason": item.reject_reason, "createdAt": item.created_at, "assets": submission_assets[item.id],
    } for item in sorted(submission_models.values(), key=lambda x: x.version, reverse=True)]
    latest_withdrawn_id = db.scalar(select(StepSubmission.id).where(
        StepSubmission.scene_work_step_id == work_step.id,
        StepSubmission.status == "withdrawn",
    ).order_by(StepSubmission.version.desc()).limit(1))
    withdrawn_asset_ids = set(db.scalars(select(StepSubmissionAsset.asset_id).where(
        StepSubmissionAsset.submission_id == (latest_withdrawn_id or -1)
    )).all())
    draft_assets = list(db.scalars(select(Asset).where(
        Asset.scene_work_step_id == work_step.id,
        or_(Asset.asset_usage == "step_draft", Asset.id.in_(withdrawn_asset_ids or {-1})),
        Asset.is_invalid.is_(False),
    ).order_by(Asset.id.desc())).all())

    feedback_asset_ids = [asset.id for _, asset in own_submission_rows]
    annotations = list(db.scalars(select(Annotation).where(
        Annotation.target_asset_id.in_(feedback_asset_ids or [-1])
    ).order_by(Annotation.id.desc())).all())
    annotation_ids = [item.id for item in annotations]
    annotation_inputs = [{
        "id": f"annotation-{item.id}", "sourceType": "director_feedback", "sourceLabel": "导演批注",
        "mediaType": "image", "originalName": item.summary or f"批注 #{item.id}",
        "url": item.merged_url or item.overlay_url, "thumbnailUrl": item.merged_url or item.overlay_url,
        "note": item.summary, "createdAt": item.created_at,
    } for item in annotations if item.merged_url or item.overlay_url]
    for attachment in db.scalars(select(AnnotationAttachment).where(
        AnnotationAttachment.annotation_id.in_(annotation_ids or [-1])
    ).order_by(AnnotationAttachment.id.desc())).all():
        annotation_inputs.append({
            "id": f"annotation-attachment-{attachment.id}", "sourceType": "director_feedback",
            "sourceLabel": "导演批注附件", "mediaType": attachment.media_type,
            "originalName": attachment.filename, "url": attachment.public_url, "thumbnailUrl": None,
            "note": None, "createdAt": attachment.created_at,
        })
    groups.append({"key": "director_feedback", "label": "导演批注和附件", "assets": annotation_inputs})
    assets = [asset for group in groups for asset in group["assets"]]
    feedback = [{
        "id": f"annotation-{item.id}", "type": "annotation", "summary": item.summary or "导演批注",
        "authorId": item.author_id, "assetId": item.target_asset_id, "frameNumber": item.frame_number,
        "timestampSeconds": item.timestamp_seconds, "overlayUrl": item.overlay_url,
        "mergedUrl": item.merged_url, "createdAt": item.created_at,
    } for item in annotations]
    for item in submission_models.values():
        if item.reject_reason:
            feedback.append({"id": f"submission-{item.id}", "type": "rejection", "summary": item.reject_reason, "createdAt": item.reviewed_at or item.updated_at})
    if progress and progress.comment:
        feedback.append({"id": f"stage-{progress.id}", "type": "stage", "summary": progress.comment, "createdAt": progress.reviewed_at or progress.updated_at})
    feedback.sort(key=lambda item: item.get("createdAt") or datetime.min.replace(tzinfo=timezone.utc), reverse=True)
    return {
        "workStepId": work_step.id,
        "groups": groups,
        "assets": assets,
        "inputAssetCount": len({(item["sourceType"], str(item["id"])) for item in assets}),
        "missingInput": bool(missing_reasons),
        "missingInputReasons": missing_reasons,
        "draftAssets": [_asset_dict(a, source_type="draft", source_label="当前工作文件") for a in draft_assets],
        "submissions": submissions,
        "feedback": feedback,
    }


def aggregate_work_step_inputs(db: Session, work_step: SceneWorkStep) -> dict:
    return _input_context(db, work_step)


def input_asset_counts(db: Session, work_step_ids: list[int]) -> dict[int, dict]:
    # Task pages are paged/small; using the same canonical aggregator keeps counts and risk flags exact.
    result = {}
    for work_step in db.scalars(select(SceneWorkStep).where(SceneWorkStep.id.in_(work_step_ids))).all():
        context = _input_context(db, work_step)
        result[work_step.id] = {
            "count": context["inputAssetCount"],
            "missing": context["missingInput"],
            "reasons": context["missingInputReasons"],
        }
    return result

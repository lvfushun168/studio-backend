from __future__ import annotations

from collections.abc import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.admin import AuditLog
from app.models.asset import Asset
from app.models.scene import Scene
from app.models.user import User
from app.models.workflow import ReviewRecord


ACTION_LABELS = {
    "scene.create": "创建镜头",
    "scene.update": "更新镜头",
    "scene.delete": "删除镜头",
    "scene.sort_update": "调整镜头顺序",
    "scene.assignment_add": "分配负责人",
    "scene.assignment_remove": "移除负责人",
    "stage.accept": "开始制作",
    "stage.rollback": "阶段回退",
    "asset.create": "创建资产记录",
    "asset.upload_initial": "上传资产",
    "asset.version_create": "上传新版本",
    "asset.update_meta": "更新资产信息",
    "asset.delete": "删除资产",
    "asset.reference_create": "引用通用资产",
    "asset.attachment_add": "添加资产附件",
    "annotation.create": "创建批注",
    "annotation.update": "更新批注",
    "annotation.delete": "删除批注",
    "annotation.attachment_add": "添加批注附件",
    "review.submit": "提交审批",
    "review.approve": "审批通过",
    "review.reject": "审批驳回",
    "review.resubmit": "重新提交",
}


def activity_payload(
    payload: dict | None = None,
    **extra,
) -> dict:
    result = dict(payload or {})
    for key, value in extra.items():
        if value is not None:
            result[key] = value
    return result


def _user_map(db: Session, user_ids: Iterable[int | None]) -> dict[int, User]:
    ids = sorted({int(user_id) for user_id in user_ids if user_id is not None})
    if not ids:
        return {}
    rows = db.scalars(select(User).where(User.id.in_(ids))).all()
    return {row.id: row for row in rows}


def _stage_label(stage_key: str | None) -> str:
    if not stage_key:
        return ""
    label_map = {
        "storyboard": "分镜",
        "layout_character": "Layout(人)",
        "layout_background": "Layout(背)",
        "keyframe": "一原",
        "keyframe_review": "一原作监",
        "ai_draw": "AI抽卡",
        "second_keyframe": "二原",
        "second_review": "二原作监",
        "inbetween": "中割",
        "correction": "修正",
        "coloring": "上色",
        "compositing": "合成",
        "final": "完成",
        "reference": "参考",
    }
    return label_map.get(stage_key, stage_key)


def _build_audit_event(log: AuditLog, user_map: dict[int, User]) -> dict:
    payload = dict(log.payload_json or {})
    actor = user_map.get(log.user_id) if log.user_id is not None else None
    action_label = ACTION_LABELS.get(log.action, log.action)
    summary = log.summary or action_label
    return {
        "id": f"audit-{log.id}",
        "source": "audit",
        "occurred_at": log.created_at,
        "action": log.action,
        "action_label": action_label,
        "summary": summary,
        "actor_id": log.user_id,
        "actor_name": actor.display_name if actor else None,
        "actor_role": actor.role if actor else None,
        "project_id": log.project_id,
        "scene_id": payload.get("sceneId"),
        "asset_id": payload.get("assetId"),
        "stage_key": payload.get("stageKey"),
        "target_type": log.target_type,
        "target_id": log.target_id,
        "target_label": payload.get("targetLabel") or payload.get("originalName") or payload.get("sceneName"),
        "from_status": payload.get("fromStatus"),
        "to_status": payload.get("toStatus"),
        "reason_category": payload.get("reasonCategory"),
        "details": payload,
    }


def _build_review_event(record: ReviewRecord, user_map: dict[int, User]) -> dict:
    actor = user_map.get(record.operator_id)
    action = f"review.{record.action}"
    summary = record.comment or f"{_stage_label(record.stage_key)} {ACTION_LABELS.get(action, record.action)}"
    return {
        "id": f"review-{record.id}",
        "source": "review",
        "occurred_at": record.created_at,
        "action": action,
        "action_label": ACTION_LABELS.get(action, record.action),
        "summary": summary,
        "actor_id": record.operator_id,
        "actor_name": actor.display_name if actor else None,
        "actor_role": actor.role if actor else None,
        "project_id": record.project_id,
        "scene_id": record.scene_id,
        "asset_id": record.extra_json.get("assetId") if record.extra_json else None,
        "stage_key": record.stage_key,
        "target_type": "scene_stage",
        "target_id": record.stage_progress_id,
        "target_label": _stage_label(record.stage_key),
        "from_status": record.from_status,
        "to_status": record.to_status,
        "reason_category": record.extra_json.get("reasonCategory") if record.extra_json else None,
        "details": {
            "comment": record.comment,
            "extra": record.extra_json or None,
        },
    }


def build_activity_events(
    db: Session,
    *,
    audit_logs: list[AuditLog] | None = None,
    review_records: list[ReviewRecord] | None = None,
) -> list[dict]:
    audit_logs = audit_logs or []
    review_records = review_records or []
    user_map = _user_map(
        db,
        [log.user_id for log in audit_logs] + [record.operator_id for record in review_records],
    )
    items = [_build_audit_event(log, user_map) for log in audit_logs]
    items.extend(_build_review_event(record, user_map) for record in review_records)
    items.sort(key=lambda item: item["occurred_at"], reverse=True)
    return items


def list_scene_activity(db: Session, scene_id: int) -> list[dict]:
    scene = db.get(Scene, scene_id)
    if not scene:
        return []
    audit_logs = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.project_id == scene.project_id)
            .order_by(AuditLog.created_at.desc())
        ).all()
    )
    filtered_audits = []
    for log in audit_logs:
        payload = log.payload_json or {}
        if log.target_type == "scene" and log.target_id == scene_id:
            filtered_audits.append(log)
            continue
        if payload.get("sceneId") == scene_id:
            filtered_audits.append(log)
    review_records = list(
        db.scalars(
            select(ReviewRecord)
            .where(ReviewRecord.scene_id == scene_id)
            .order_by(ReviewRecord.created_at.desc())
        ).all()
    )
    return build_activity_events(db, audit_logs=filtered_audits, review_records=review_records)


def list_asset_activity(db: Session, asset_id: int) -> list[dict]:
    asset = db.get(Asset, asset_id)
    if not asset:
        return []
    if asset.scene_id is not None:
        asset_group = db.scalars(
            select(Asset).where(
                Asset.scene_id == asset.scene_id,
                Asset.stage_key == asset.stage_key,
                Asset.asset_type == asset.asset_type,
                Asset.original_name == asset.original_name,
            )
        ).all()
    else:
        asset_group = db.scalars(
            select(Asset).where(
                Asset.scene_group_id == asset.scene_group_id,
                Asset.stage_key == asset.stage_key,
                Asset.asset_type == asset.asset_type,
                Asset.original_name == asset.original_name,
            )
        ).all()
    asset_ids = {item.id for item in asset_group}
    audit_logs = list(
        db.scalars(
            select(AuditLog)
            .where(AuditLog.project_id == asset.project_id)
            .order_by(AuditLog.created_at.desc())
        ).all()
    )
    filtered_audits = []
    for log in audit_logs:
        payload = log.payload_json or {}
        if log.target_type == "asset" and log.target_id in asset_ids:
            filtered_audits.append(log)
            continue
        if payload.get("assetId") in asset_ids:
            filtered_audits.append(log)
            continue
        if (
            payload.get("sceneId") == asset.scene_id
            and payload.get("stageKey") == asset.stage_key
            and payload.get("originalName") == asset.original_name
        ):
            filtered_audits.append(log)
    return build_activity_events(db, audit_logs=filtered_audits, review_records=[])


def list_admin_activity(
    db: Session,
    *,
    action: str | None = None,
    target_type: str | None = None,
    user_id: int | None = None,
    project_id: int | None = None,
    scene_id: int | None = None,
    asset_id: int | None = None,
    limit: int = 200,
) -> list[dict]:
    audit_stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if action is not None and not action.startswith("review."):
        audit_stmt = audit_stmt.where(AuditLog.action == action)
    if target_type is not None:
        audit_stmt = audit_stmt.where(AuditLog.target_type == target_type)
    if user_id is not None:
        audit_stmt = audit_stmt.where(AuditLog.user_id == user_id)
    if project_id is not None:
        audit_stmt = audit_stmt.where(AuditLog.project_id == project_id)
    audit_logs = list(db.scalars(audit_stmt.limit(limit)).all())
    if scene_id is not None or asset_id is not None:
        scoped_audits = []
        for log in audit_logs:
            payload = log.payload_json or {}
            if scene_id is not None and payload.get("sceneId") != scene_id and log.target_id != scene_id:
                continue
            if asset_id is not None and payload.get("assetId") != asset_id and log.target_id != asset_id:
                continue
            scoped_audits.append(log)
        audit_logs = scoped_audits

    review_stmt = select(ReviewRecord).order_by(ReviewRecord.created_at.desc())
    if user_id is not None:
        review_stmt = review_stmt.where(ReviewRecord.operator_id == user_id)
    if project_id is not None:
        review_stmt = review_stmt.where(ReviewRecord.project_id == project_id)
    if scene_id is not None:
        review_stmt = review_stmt.where(ReviewRecord.scene_id == scene_id)
    if action is not None and action.startswith("review."):
        review_stmt = review_stmt.where(ReviewRecord.action == action.split(".", 1)[1])
    review_records = list(db.scalars(review_stmt.limit(limit)).all())
    events = build_activity_events(db, audit_logs=audit_logs, review_records=review_records)
    return events[:limit]

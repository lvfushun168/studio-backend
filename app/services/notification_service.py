from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.notification import Notification
from app.models.project import UserProjectMembership
from app.models.user import User
from app.models.work_step import SceneWorkStep


def create_notification(
    db: Session, *, project_id: int, user_id: int, notification_type: str,
    title: str, content: str, payload: dict | None = None,
) -> Notification:
    notification = Notification(
        project_id=project_id, user_id=user_id, type=notification_type,
        title=title, content=content, status="unread", payload_json=payload,
    )
    db.add(notification)
    return notification


def project_role_user_ids(db: Session, project_id: int, roles: set[str]) -> set[int]:
    memberships = list(db.scalars(select(UserProjectMembership).where(
        UserProjectMembership.project_id == project_id
    )).all())
    users = {user.id: user for user in db.scalars(select(User).where(
        User.id.in_([item.user_id for item in memberships] or [-1]), User.is_active.is_(True)
    )).all()}
    return {
        membership.user_id for membership in memberships
        if membership.user_id in users and (membership.role_in_project or users[membership.user_id].role) in roles
    }


def notify_users_for_step(
    db: Session, work_step: SceneWorkStep, user_ids: set[int], notification_type: str,
    title: str, content: str, *, exclude_user_id: int | None = None,
) -> None:
    payload = {
        "scene_id": work_step.scene_id, "stage": work_step.stage_key,
        "work_step_id": work_step.id,
    }
    for user_id in sorted(user_ids - ({exclude_user_id} if exclude_user_id else set())):
        create_notification(
            db, project_id=work_step.project_id, user_id=user_id,
            notification_type=notification_type, title=title, content=content, payload=payload,
        )


def notify_step_schedule_change(
    db: Session, work_step: SceneWorkStep, *, old_assignee_id: int | None,
    new_assignee_id: int | None, assignee_changed: bool, due_changed: bool,
    operator_id: int,
) -> None:
    if assignee_changed:
        recipients = {value for value in (old_assignee_id, new_assignee_id) if value}
        action = "步骤负责人已变更" if old_assignee_id else "你有新的步骤任务"
        notify_users_for_step(
            db, work_step, recipients, "work_step_assigned", action,
            f"{work_step.stage_key} / {work_step.name} 的负责人已更新",
            exclude_user_id=operator_id,
        )
    if due_changed and new_assignee_id:
        due_text = work_step.due_at.isoformat() if work_step.due_at else "未设置"
        notify_users_for_step(
            db, work_step, {new_assignee_id}, "work_step_due_changed", "步骤截止时间已变更",
            f"{work_step.stage_key} / {work_step.name} 的截止时间更新为 {due_text}",
            exclude_user_id=operator_id,
        )

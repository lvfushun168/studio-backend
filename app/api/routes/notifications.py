from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser
from app.core.database import get_db
from app.models.notification import Notification
from app.schemas.notification import NotificationBatchRead, NotificationRead

router = APIRouter()


@router.get("", response_model=list[NotificationRead])
def list_notifications(
    project_id: int | None = None,
    status: str | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[Notification]:
    """List notifications for the current user."""
    stmt = select(Notification).where(Notification.user_id == current_user.id).order_by(Notification.id.desc())
    if project_id is not None:
        stmt = stmt.where(Notification.project_id == project_id)
    if status is not None:
        stmt = stmt.where(Notification.status == status)
    return list(db.scalars(stmt).all())


@router.post("/{notification_id}/read", response_model=NotificationRead)
def mark_read(
    notification_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Notification:
    notification = db.get(Notification, notification_id)
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    if notification.user_id != current_user.id and current_user.role != "admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Not your notification")
    notification.status = "read"
    notification.read_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(notification)
    return notification


@router.post("/batch-read", status_code=status.HTTP_204_NO_CONTENT)
def batch_mark_read(
    payload: NotificationBatchRead,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    stmt = select(Notification).where(
        Notification.id.in_(payload.ids),
        Notification.user_id == current_user.id,
    )
    notifications = db.scalars(stmt).all()
    for n in notifications:
        n.status = "read"
        n.read_at = datetime.now(timezone.utc)
    db.commit()


@router.post("/mark-all-read", status_code=status.HTTP_204_NO_CONTENT)
def mark_all_read(
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    """Mark all unread notifications for the current user as read."""
    stmt = select(Notification).where(
        Notification.user_id == current_user.id,
        Notification.status == "unread",
    )
    notifications = db.scalars(stmt).all()
    for n in notifications:
        n.status = "read"
        n.read_at = datetime.now(timezone.utc)
    db.commit()

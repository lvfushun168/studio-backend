from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.notification import Notification
from app.schemas.notification import NotificationBatchRead, NotificationRead

router = APIRouter()


@router.get("", response_model=list[NotificationRead])
def list_notifications(
    user_id: int | None = None,
    project_id: int | None = None,
    status: str | None = None,
    db: Session = Depends(get_db),
) -> list[Notification]:
    stmt = select(Notification).order_by(Notification.id.desc())
    if user_id is not None:
        stmt = stmt.where(Notification.user_id == user_id)
    if project_id is not None:
        stmt = stmt.where(Notification.project_id == project_id)
    if status is not None:
        stmt = stmt.where(Notification.status == status)
    return list(db.scalars(stmt).all())


@router.post("/{notification_id}/read", response_model=NotificationRead)
def mark_read(notification_id: int, db: Session = Depends(get_db)) -> Notification:
    notification = db.get(Notification, notification_id)
    if not notification:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Notification not found")
    notification.status = "read"
    db.commit()
    db.refresh(notification)
    return notification


@router.post("/batch-read", status_code=status.HTTP_204_NO_CONTENT)
def batch_mark_read(payload: NotificationBatchRead, db: Session = Depends(get_db)) -> None:
    stmt = select(Notification).where(Notification.id.in_(payload.ids))
    notifications = db.scalars(stmt).all()
    for n in notifications:
        n.status = "read"
    db.commit()

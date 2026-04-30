from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import ADMIN_ROLES, CurrentUser, require_role
from app.core.database import get_db
from app.models.admin import AccountPoolAccount, AuditLog, GenerationResult, GenerationTask
from app.models.project import Project
from app.models.user import User
from app.schemas.admin import AuditLogRead, DashboardRead, DashboardStatusCount, GenerationTaskRead

router = APIRouter()


@router.get("/dashboard", response_model=DashboardRead)
def get_dashboard(current_user: CurrentUser, db: Session = Depends(get_db)) -> DashboardRead:
    require_role(ADMIN_ROLES)(current_user)
    account_count = db.scalar(select(func.count(AccountPoolAccount.id))) or 0
    user_count = db.scalar(select(func.count(User.id))) or 0
    project_count = db.scalar(select(func.count(Project.id))) or 0
    task_count = db.scalar(select(func.count(GenerationTask.id))) or 0
    result_count = db.scalar(select(func.count(GenerationResult.id))) or 0
    pending_review_count = db.scalar(select(func.count(GenerationResult.id)).where(GenerationResult.status == "submitted")) or 0
    status_rows = db.execute(
        select(AccountPoolAccount.status, func.count(AccountPoolAccount.id)).group_by(AccountPoolAccount.status)
    ).all()
    recent_tasks = list(db.scalars(select(GenerationTask).order_by(GenerationTask.created_at.desc()).limit(5)).all())
    return DashboardRead(
        account_count=account_count,
        user_count=user_count,
        project_count=project_count,
        task_count=task_count,
        result_count=result_count,
        pending_review_count=pending_review_count,
        account_statuses=[DashboardStatusCount(key=row[0], count=row[1]) for row in status_rows],
        recent_tasks=[GenerationTaskRead.model_validate(item) for item in recent_tasks],
    )


@router.get("/audit-logs", response_model=list[AuditLogRead])
def list_audit_logs(
    action: str | None = None,
    target_type: str | None = None,
    user_id: int | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[AuditLog]:
    require_role(ADMIN_ROLES)(current_user)
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc())
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if target_type is not None:
        stmt = stmt.where(AuditLog.target_type == target_type)
    if user_id is not None:
        stmt = stmt.where(AuditLog.user_id == user_id)
    return list(db.scalars(stmt).all())

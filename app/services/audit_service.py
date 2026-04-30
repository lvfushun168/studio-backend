from sqlalchemy.orm import Session

from app.models.admin import AuditLog


def record_audit(
    db: Session,
    *,
    user_id: int | None,
    action: str,
    target_type: str,
    target_id: int | None = None,
    project_id: int | None = None,
    summary: str | None = None,
    payload_json: dict | None = None,
) -> AuditLog:
    log = AuditLog(
        user_id=user_id,
        project_id=project_id,
        action=action,
        target_type=target_type,
        target_id=target_id,
        summary=summary,
        payload_json=payload_json,
    )
    db.add(log)
    return log

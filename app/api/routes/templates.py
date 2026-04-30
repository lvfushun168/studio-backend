from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_accessible_project_ids, require_project_access
from app.core.database import get_db
from app.models.admin import GenerationTemplate
from app.schemas.admin import GenerationTemplateCreate, GenerationTemplateRead, GenerationTemplateUpdate
from app.services.audit_service import record_audit

router = APIRouter()


@router.get("", response_model=list[GenerationTemplateRead])
def list_templates(
    project_id: int | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[GenerationTemplate]:
    stmt = select(GenerationTemplate).order_by(GenerationTemplate.id.desc())
    if current_user.role != "admin":
        accessible_ids = get_accessible_project_ids(current_user, db)
        stmt = stmt.where(
            or_(
                GenerationTemplate.user_id == current_user.id,
                GenerationTemplate.project_id.in_(accessible_ids),
            )
        )
    if project_id is not None:
        require_project_access(project_id, current_user, db)
        stmt = stmt.where(or_(GenerationTemplate.project_id == project_id, GenerationTemplate.user_id == current_user.id))
    return list(db.scalars(stmt).all())


@router.post("", response_model=GenerationTemplateRead, status_code=status.HTTP_201_CREATED)
def create_template(payload: GenerationTemplateCreate, current_user: CurrentUser, db: Session = Depends(get_db)) -> GenerationTemplate:
    if payload.project_id is not None:
        require_project_access(payload.project_id, current_user, db)
    template = GenerationTemplate(
        name=payload.name,
        description=payload.description,
        snapshot_json=payload.snapshot,
        user_id=payload.user_id if current_user.role == "admin" else current_user.id if payload.project_id is None else None,
        project_id=payload.project_id,
        created_by=current_user.id,
    )
    db.add(template)
    record_audit(db, user_id=current_user.id, action="template.create", target_type="template", target_id=None, project_id=payload.project_id, summary=f"Created template {payload.name}")
    db.commit()
    return template


@router.put("/{template_id}", response_model=GenerationTemplateRead)
def update_template(template_id: int, payload: GenerationTemplateUpdate, current_user: CurrentUser, db: Session = Depends(get_db)) -> GenerationTemplate:
    template = db.get(GenerationTemplate, template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    if current_user.role != "admin":
        if template.user_id != current_user.id:
            if template.project_id is None:
                raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Template access denied")
            require_project_access(template.project_id, current_user, db)
    for field in ["name", "description", "snapshot", "user_id", "project_id"]:
        source = "snapshot_json" if field == "snapshot" else field
        value = getattr(payload, field)
        if value is not None:
            setattr(template, source, value)
    record_audit(db, user_id=current_user.id, action="template.update", target_type="template", target_id=template.id, project_id=template.project_id, summary=f"Updated template {template.name}")
    db.commit()
    return template


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_template(template_id: int, current_user: CurrentUser, db: Session = Depends(get_db)) -> None:
    template = db.get(GenerationTemplate, template_id)
    if not template:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Template not found")
    if current_user.role != "admin" and template.user_id != current_user.id:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Template access denied")
    db.delete(template)
    db.commit()

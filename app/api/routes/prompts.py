from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_accessible_project_ids, require_project_access
from app.core.database import get_db
from app.models.admin import PromptTemplate
from app.schemas.admin import PromptCreate, PromptRead, PromptUpdate
from app.services.audit_service import record_audit

router = APIRouter()
@router.get("", response_model=list[PromptRead])
def list_prompts(
    project_id: int | None = None,
    scope: str | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[PromptTemplate]:
    stmt = select(PromptTemplate).order_by(PromptTemplate.id.desc())
    if current_user.role != "admin":
        accessible_ids = get_accessible_project_ids(current_user, db)
        stmt = stmt.where(
            or_(
                PromptTemplate.scope == "global",
                PromptTemplate.user_id == current_user.id,
                PromptTemplate.project_id.in_(accessible_ids),
            )
        )
    if project_id is not None:
        require_project_access(project_id, current_user, db)
        stmt = stmt.where(or_(PromptTemplate.project_id == project_id, PromptTemplate.scope == "global", PromptTemplate.user_id == current_user.id))
    if scope is not None:
        stmt = stmt.where(PromptTemplate.scope == scope)
    return list(db.scalars(stmt).all())


@router.post("", response_model=PromptRead, status_code=status.HTTP_201_CREATED)
def create_prompt(payload: PromptCreate, current_user: CurrentUser, db: Session = Depends(get_db)) -> PromptTemplate:
    if payload.project_id is not None:
        require_project_access(payload.project_id, current_user, db)
    prompt = PromptTemplate(
        name=payload.name,
        content=payload.content,
        aspect_ratio=payload.aspect_ratio,
        resolution=payload.resolution,
        scope=payload.scope,
        project_id=payload.project_id,
        user_id=payload.user_id if current_user.role == "admin" else current_user.id if payload.scope == "private" else payload.user_id,
        is_active=payload.is_active,
        created_by=current_user.id,
    )
    db.add(prompt)
    record_audit(db, user_id=current_user.id, action="prompt.create", target_type="prompt", summary=f"Created prompt {payload.name}", project_id=payload.project_id)
    db.commit()
    return prompt


@router.put("/{prompt_id}", response_model=PromptRead)
def update_prompt(prompt_id: int, payload: PromptUpdate, current_user: CurrentUser, db: Session = Depends(get_db)) -> PromptTemplate:
    prompt = db.get(PromptTemplate, prompt_id)
    if not prompt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found")
    if current_user.role != "admin":
        if prompt.user_id != current_user.id and not (prompt.project_id and prompt.scope == "project"):
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Prompt access denied")
        if prompt.project_id is not None:
            require_project_access(prompt.project_id, current_user, db)
    for field in ["name", "content", "aspect_ratio", "resolution", "scope", "project_id", "user_id", "is_active"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(prompt, field, value)
    record_audit(db, user_id=current_user.id, action="prompt.update", target_type="prompt", target_id=prompt.id, project_id=prompt.project_id, summary=f"Updated prompt {prompt.name}")
    db.commit()
    return prompt


@router.delete("/{prompt_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_prompt(prompt_id: int, current_user: CurrentUser, db: Session = Depends(get_db)) -> None:
    prompt = db.get(PromptTemplate, prompt_id)
    if not prompt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found")
    if current_user.role != "admin":
        if prompt.user_id != current_user.id:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Prompt access denied")
    record_audit(db, user_id=current_user.id, action="prompt.delete", target_type="prompt", target_id=prompt.id, project_id=prompt.project_id, summary=f"Deleted prompt {prompt.name}")
    db.delete(prompt)
    db.commit()


@router.post("/{prompt_id}/touch", response_model=PromptRead)
def touch_prompt(prompt_id: int, current_user: CurrentUser, db: Session = Depends(get_db)) -> PromptTemplate:
    prompt = db.get(PromptTemplate, prompt_id)
    if not prompt:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Prompt not found")
    if prompt.project_id is not None:
        require_project_access(prompt.project_id, current_user, db)
    prompt.use_count += 1
    prompt.last_used_at = datetime.now(timezone.utc)
    db.commit()
    return prompt

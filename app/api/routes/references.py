from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_project_access
from app.core.database import get_db
from app.models.reference import Reference
from app.schemas.reference import ReferenceCreate, ReferenceRead

router = APIRouter()


@router.get("", response_model=list[ReferenceRead])
def list_references(
    project_id: int | None = None,
    source_type: str | None = None,
    source_id: int | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[Reference]:
    stmt = select(Reference).order_by(Reference.id.desc())
    if project_id is not None:
        stmt = stmt.where(Reference.project_id == project_id)
    if source_type is not None:
        stmt = stmt.where(Reference.source_type == source_type)
    if source_id is not None:
        stmt = stmt.where(Reference.source_id == source_id)
    if target_type is not None:
        stmt = stmt.where(Reference.target_type == target_type)
    if target_id is not None:
        stmt = stmt.where(Reference.target_id == target_id)
    return list(db.scalars(stmt).all())


@router.post("", response_model=ReferenceRead, status_code=status.HTTP_201_CREATED)
def create_reference(
    payload: ReferenceCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Reference:
    require_project_access(payload.project_id, current_user, db)
    ref = Reference(
        project_id=payload.project_id,
        source_type=payload.source_type,
        source_id=payload.source_id,
        target_type=payload.target_type,
        target_id=payload.target_id,
        relation_type=payload.relation_type,
        created_by=current_user.id,
    )
    db.add(ref)
    db.commit()
    db.refresh(ref)
    return ref


@router.get("/{ref_id}", response_model=ReferenceRead)
def get_reference(
    ref_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Reference:
    ref = db.get(Reference, ref_id)
    if not ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference not found")
    require_project_access(ref.project_id, current_user, db)
    return ref


@router.delete("/{ref_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_reference(
    ref_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    ref = db.get(Reference, ref_id)
    if not ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Reference not found")
    require_project_access(ref.project_id, current_user, db)
    db.delete(ref)
    db.commit()

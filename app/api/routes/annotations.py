from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, DIRECTOR_ROLES, get_accessible_project_ids, require_project_access, require_role
from app.core.database import get_db
from app.models.annotation import Annotation
from app.models.asset import Asset
from app.schemas.annotation import AnnotationCreate, AnnotationRead

router = APIRouter()


@router.get("", response_model=list[AnnotationRead])
def list_annotations(
    asset_id: int | None = None,
    asset_version: int | None = None,
    frame_number: int | None = None,
    project_id: int | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[Annotation]:
    stmt = select(Annotation).order_by(Annotation.id.desc())
    if project_id is not None:
        require_project_access(project_id, current_user, db)
        stmt = stmt.where(Annotation.project_id == project_id)
    elif asset_id is not None:
        asset = db.get(Asset, asset_id)
        if not asset:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
        require_project_access(asset.project_id, current_user, db)
    elif current_user.role != "admin":
        accessible_project_ids = get_accessible_project_ids(current_user, db)
        if not accessible_project_ids:
            return []
        stmt = stmt.where(Annotation.project_id.in_(accessible_project_ids))

    if asset_id is not None:
        stmt = stmt.where(Annotation.target_asset_id == asset_id)
    if asset_version is not None:
        stmt = stmt.where(Annotation.target_version == asset_version)
    if frame_number is not None:
        stmt = stmt.where(Annotation.frame_number == frame_number)
    return list(db.scalars(stmt).all())


@router.post("", response_model=AnnotationRead, status_code=status.HTTP_201_CREATED)
def create_annotation(
    payload: AnnotationCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Annotation:
    require_role(DIRECTOR_ROLES)(current_user)
    require_project_access(payload.project_id, current_user, db)
    annotation = Annotation(
        project_id=payload.project_id,
        target_asset_id=payload.target_asset_id,
        target_version=payload.target_version,
        author_id=current_user.id,
        author_role=current_user.role,
        frame_number=payload.frame_number,
        timestamp_seconds=payload.timestamp_seconds,
        canvas_json=payload.canvas_json,
        summary=payload.summary,
    )
    db.add(annotation)
    db.commit()
    db.refresh(annotation)
    return annotation


@router.get("/{annotation_id}", response_model=AnnotationRead)
def get_annotation(
    annotation_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Annotation:
    annotation = db.get(Annotation, annotation_id)
    if not annotation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")
    require_project_access(annotation.project_id, current_user, db)
    return annotation


@router.delete("/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_annotation(
    annotation_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    annotation = db.get(Annotation, annotation_id)
    if not annotation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")
    require_project_access(annotation.project_id, current_user, db)
    if annotation.author_id != current_user.id and current_user.role not in ("admin", "director"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot delete others' annotations")
    db.delete(annotation)
    db.commit()

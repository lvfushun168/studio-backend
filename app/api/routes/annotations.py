from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.annotation import Annotation
from app.schemas.annotation import AnnotationCreate, AnnotationRead

router = APIRouter()


@router.get("", response_model=list[AnnotationRead])
def list_annotations(
    asset_id: int | None = None,
    asset_version: int | None = None,
    frame_number: int | None = None,
    db: Session = Depends(get_db),
) -> list[Annotation]:
    stmt = select(Annotation).order_by(Annotation.id.desc())
    if asset_id is not None:
        stmt = stmt.where(Annotation.target_asset_id == asset_id)
    if asset_version is not None:
        stmt = stmt.where(Annotation.target_version == asset_version)
    if frame_number is not None:
        stmt = stmt.where(Annotation.frame_number == frame_number)
    return list(db.scalars(stmt).all())


@router.post("", response_model=AnnotationRead, status_code=status.HTTP_201_CREATED)
def create_annotation(payload: AnnotationCreate, db: Session = Depends(get_db)) -> Annotation:
    annotation = Annotation(
        project_id=payload.project_id,
        target_asset_id=payload.target_asset_id,
        target_version=payload.target_version,
        author_id=payload.author_id,
        author_role=payload.author_role,
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
def get_annotation(annotation_id: int, db: Session = Depends(get_db)) -> Annotation:
    annotation = db.get(Annotation, annotation_id)
    if not annotation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")
    return annotation


@router.delete("/{annotation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_annotation(annotation_id: int, db: Session = Depends(get_db)) -> None:
    annotation = db.get(Annotation, annotation_id)
    if not annotation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")
    db.delete(annotation)
    db.commit()

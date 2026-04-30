from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.core.auth import CurrentUser, DIRECTOR_ROLES, get_accessible_project_ids, require_project_access, require_role
from app.core.database import get_db
from app.models.annotation import Annotation, AnnotationAttachment
from app.models.asset import Asset
from app.schemas.annotation import AnnotationCreate, AnnotationRead, AnnotationUpdate
from app.services.media_service import generate_annotation_artifacts

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
    stmt = select(Annotation).options(selectinload(Annotation.attachments)).order_by(Annotation.id.desc())
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
    asset = db.get(Asset, payload.target_asset_id)
    if not asset or asset.project_id != payload.project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Target asset not found in project")
    annotation = Annotation(
        project_id=payload.project_id,
        target_asset_id=payload.target_asset_id,
        target_version=payload.target_version or asset.version,
        author_id=current_user.id,
        author_role=current_user.role,
        frame_number=payload.frame_number,
        timestamp_seconds=payload.timestamp_seconds,
        canvas_json=payload.canvas_json or {"objects": []},
        overlay_url=payload.overlay_url,
        merged_url=payload.merged_url,
        summary=payload.summary,
    )
    db.add(annotation)
    db.flush()
    generated = generate_annotation_artifacts(annotation, asset)
    annotation.overlay_path = generated["overlay_path"]
    annotation.overlay_url = payload.overlay_url or generated["overlay_url"]
    annotation.merged_path = generated["merged_path"]
    annotation.merged_url = payload.merged_url or generated["merged_url"]
    db.commit()
    stmt = select(Annotation).options(selectinload(Annotation.attachments)).where(Annotation.id == annotation.id)
    return db.scalar(stmt)


@router.get("/{annotation_id}", response_model=AnnotationRead)
def get_annotation(
    annotation_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Annotation:
    stmt = select(Annotation).options(selectinload(Annotation.attachments)).where(Annotation.id == annotation_id)
    annotation = db.scalar(stmt)
    if not annotation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")
    require_project_access(annotation.project_id, current_user, db)
    return annotation


@router.put("/{annotation_id}", response_model=AnnotationRead)
def update_annotation(
    annotation_id: int,
    payload: AnnotationUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Annotation:
    stmt = select(Annotation).options(selectinload(Annotation.attachments)).where(Annotation.id == annotation_id)
    annotation = db.scalar(stmt)
    if not annotation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")
    require_project_access(annotation.project_id, current_user, db)
    if annotation.author_id != current_user.id and current_user.role not in ("admin", "director"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Cannot edit others' annotations")

    regenerate = False
    for field in ("frame_number", "timestamp_seconds", "canvas_json", "summary"):
        value = getattr(payload, field)
        if value is not None:
            setattr(annotation, field, value)
            regenerate = True
    if payload.overlay_url is not None:
        annotation.overlay_url = payload.overlay_url
    if payload.merged_url is not None:
        annotation.merged_url = payload.merged_url
    if regenerate:
        asset = db.get(Asset, annotation.target_asset_id)
        generated = generate_annotation_artifacts(annotation, asset)
        annotation.overlay_path = generated["overlay_path"]
        if payload.overlay_url is None:
            annotation.overlay_url = generated["overlay_url"]
        annotation.merged_path = generated["merged_path"]
        if payload.merged_url is None:
            annotation.merged_url = generated["merged_url"]

    db.commit()
    stmt = select(Annotation).options(selectinload(Annotation.attachments)).where(Annotation.id == annotation_id)
    return db.scalar(stmt)


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


class AnnotationAttachmentCreatePayload(BaseModel):
    filename: str
    media_type: str = "binary"
    public_url: str
    size_bytes: int | None = None


@router.post("/{annotation_id}/attachments", response_model=dict)
def create_annotation_attachment_meta(
    annotation_id: int,
    payload: AnnotationAttachmentCreatePayload,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    annotation = db.get(Annotation, annotation_id)
    if not annotation:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Annotation not found")
    require_project_access(annotation.project_id, current_user, db)
    attachment = AnnotationAttachment(
        annotation_id=annotation_id,
        filename=payload.filename,
        media_type=payload.media_type,
        storage_path="",
        public_url=payload.public_url,
        size_bytes=payload.size_bytes,
        uploaded_by=current_user.id,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return {"attachment_id": attachment.id, "annotation_id": annotation_id, "filename": attachment.filename}

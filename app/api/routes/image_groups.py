from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import or_, select
from sqlalchemy.orm import Session, selectinload

from app.core.auth import CurrentUser, get_accessible_project_ids, require_project_access
from app.core.database import get_db
from app.models.admin import ImageGroup, ImageGroupImage
from app.schemas.admin import (
    ImageGroupCreate,
    ImageGroupImageCreate,
    ImageGroupImageRead,
    ImageGroupImageUpdate,
    ImageGroupRead,
    ImageGroupUpdate,
)
from app.services.audit_service import record_audit

router = APIRouter()


def _load_group(db: Session, group_id: int) -> ImageGroup | None:
    stmt = select(ImageGroup).options(selectinload(ImageGroup.images)).where(ImageGroup.id == group_id)
    return db.scalar(stmt)


@router.get("", response_model=list[ImageGroupRead])
def list_image_groups(
    project_id: int | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[ImageGroup]:
    stmt = select(ImageGroup).options(selectinload(ImageGroup.images)).order_by(ImageGroup.id.desc())
    if current_user.role != "admin":
        accessible_ids = get_accessible_project_ids(current_user, db)
        stmt = stmt.where(
            or_(
                ImageGroup.user_id == current_user.id,
                ImageGroup.project_id.in_(accessible_ids),
                ImageGroup.project_id.is_(None),
            )
        )
    if project_id is not None:
        require_project_access(project_id, current_user, db)
        stmt = stmt.where(or_(ImageGroup.project_id == project_id, ImageGroup.project_id.is_(None)))
    return list(db.scalars(stmt).all())


@router.post("", response_model=ImageGroupRead, status_code=status.HTTP_201_CREATED)
def create_image_group(payload: ImageGroupCreate, current_user: CurrentUser, db: Session = Depends(get_db)) -> ImageGroup:
    if payload.project_id is not None:
        require_project_access(payload.project_id, current_user, db)
    owner_id = payload.user_id if current_user.role == "admin" else current_user.id
    group = ImageGroup(
        name=payload.name,
        description=payload.description,
        project_id=payload.project_id,
        user_id=owner_id,
        is_shared=payload.is_shared,
    )
    db.add(group)
    db.flush()
    for image in payload.images:
        db.add(
            ImageGroupImage(
                image_group_id=group.id,
                name=image.name,
                url=image.url,
                thumbnail_url=image.thumbnail_url,
                sort_order=image.sort_order,
                metadata_json=image.metadata_json,
            )
        )
    record_audit(db, user_id=current_user.id, action="image_group.create", target_type="image_group", target_id=group.id, project_id=group.project_id, summary=f"Created image group {group.name}")
    db.commit()
    return _load_group(db, group.id)


@router.put("/{group_id}", response_model=ImageGroupRead)
def update_image_group(group_id: int, payload: ImageGroupUpdate, current_user: CurrentUser, db: Session = Depends(get_db)) -> ImageGroup:
    group = _load_group(db, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image group not found")
    if current_user.role != "admin" and group.user_id != current_user.id:
        if group.project_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Image group access denied")
        require_project_access(group.project_id, current_user, db)
    for field in ["name", "description", "project_id", "user_id", "is_shared"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(group, field, value)
    record_audit(db, user_id=current_user.id, action="image_group.update", target_type="image_group", target_id=group.id, project_id=group.project_id, summary=f"Updated image group {group.name}")
    db.commit()
    return _load_group(db, group.id)


@router.post("/{group_id}/images", response_model=ImageGroupImageRead, status_code=status.HTTP_201_CREATED)
def create_image_group_image(group_id: int, payload: ImageGroupImageCreate, current_user: CurrentUser, db: Session = Depends(get_db)) -> ImageGroupImage:
    group = db.get(ImageGroup, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image group not found")
    if current_user.role != "admin" and group.user_id != current_user.id:
        if group.project_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Image group access denied")
        require_project_access(group.project_id, current_user, db)
    image = ImageGroupImage(
        image_group_id=group_id,
        name=payload.name,
        url=payload.url,
        thumbnail_url=payload.thumbnail_url,
        sort_order=payload.sort_order,
        metadata_json=payload.metadata_json,
    )
    db.add(image)
    record_audit(db, user_id=current_user.id, action="image_group.image_create", target_type="image_group_image", target_id=None, project_id=group.project_id, summary=f"Added image to group {group.name}")
    db.commit()
    return image


@router.put("/images/{image_id}", response_model=ImageGroupImageRead)
def update_image_group_image(image_id: int, payload: ImageGroupImageUpdate, current_user: CurrentUser, db: Session = Depends(get_db)) -> ImageGroupImage:
    image = db.get(ImageGroupImage, image_id)
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    group = db.get(ImageGroup, image.image_group_id)
    if current_user.role != "admin" and group.user_id != current_user.id:
        if group.project_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Image group access denied")
        require_project_access(group.project_id, current_user, db)
    for field in ["name", "url", "thumbnail_url", "sort_order", "metadata_json"]:
        value = getattr(payload, field)
        if value is not None:
            setattr(image, field, value)
    db.commit()
    return image


@router.delete("/images/{image_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_image_group_image(image_id: int, current_user: CurrentUser, db: Session = Depends(get_db)) -> None:
    image = db.get(ImageGroupImage, image_id)
    if not image:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image not found")
    group = db.get(ImageGroup, image.image_group_id)
    if current_user.role != "admin" and group.user_id != current_user.id:
        if group.project_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Image group access denied")
        require_project_access(group.project_id, current_user, db)
    db.delete(image)
    db.commit()


@router.delete("/{group_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_image_group(group_id: int, current_user: CurrentUser, db: Session = Depends(get_db)) -> None:
    group = db.get(ImageGroup, group_id)
    if not group:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Image group not found")
    if current_user.role != "admin" and group.user_id != current_user.id:
        if group.project_id is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Image group access denied")
        require_project_access(group.project_id, current_user, db)
    db.delete(group)
    db.commit()

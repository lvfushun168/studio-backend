from fastapi import APIRouter, Depends, HTTPException, Query, status
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.auth import CurrentUser, get_accessible_project_ids, require_project_access
from app.core.database import get_db
from app.models.asset import Asset, AssetAttachment
from app.schemas.asset import AssetCreate, AssetRead, AssetUpdate

router = APIRouter()


@router.get("", response_model=list[AssetRead])
def list_assets(
    project_id: int | None = None,
    scene_id: int | None = None,
    scene_group_id: int | None = None,
    stage_key: str | None = None,
    is_global: bool | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[Asset]:
    stmt = select(Asset).options(selectinload(Asset.attachments)).order_by(Asset.id.desc())
    if project_id is not None:
        require_project_access(project_id, current_user, db)
        stmt = stmt.where(Asset.project_id == project_id)
    elif current_user.role != "admin":
        accessible_project_ids = get_accessible_project_ids(current_user, db)
        if not accessible_project_ids:
            return []
        stmt = stmt.where(Asset.project_id.in_(accessible_project_ids))
    if scene_id is not None:
        stmt = stmt.where(Asset.scene_id == scene_id)
    if scene_group_id is not None:
        stmt = stmt.where(Asset.scene_group_id == scene_group_id)
    if stage_key is not None:
        stmt = stmt.where(Asset.stage_key == stage_key)
    if is_global is not None:
        stmt = stmt.where(Asset.is_global == is_global)
    return list(db.scalars(stmt).all())


@router.get("/latest", response_model=list[AssetRead])
def list_latest_assets(
    project_id: int,
    scene_id: int | None = None,
    scene_group_id: int | None = None,
    stage_key: str | None = None,
    is_global: bool | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[Asset]:
    """Return only the latest version of each asset group."""
    require_project_access(project_id, current_user, db)

    # Build base filter
    base_where = [Asset.project_id == project_id]
    if scene_id is not None:
        base_where.append(Asset.scene_id == scene_id)
    if scene_group_id is not None:
        base_where.append(Asset.scene_group_id == scene_group_id)
    if stage_key is not None:
        base_where.append(Asset.stage_key == stage_key)
    if is_global is not None:
        base_where.append(Asset.is_global == is_global)

    # Find max version per group
    group_cols = [Asset.scene_id, Asset.scene_group_id, Asset.stage_key, Asset.original_name]
    subq = (
        select(
            Asset.scene_id,
            Asset.scene_group_id,
            Asset.stage_key,
            Asset.original_name,
            func.max(Asset.version).label("max_version"),
        )
        .where(*base_where)
        .group_by(*group_cols)
        .subquery()
    )

    stmt = (
        select(Asset)
        .join(
            subq,
            (
                Asset.scene_id == subq.c.scene_id
                if scene_id is not None or is_global is not True
                else Asset.scene_group_id == subq.c.scene_group_id
            )
            & (Asset.stage_key == subq.c.stage_key)
            & (Asset.original_name == subq.c.original_name)
            & (Asset.version == subq.c.max_version),
        )
        .where(*base_where)
        .order_by(Asset.id.desc())
    )

    # Simpler approach: use window function or just fetch all and filter in Python
    # For MVP correctness over performance, let's do the subquery properly
    stmt = select(Asset).options(selectinload(Asset.attachments)).where(*base_where).order_by(Asset.id.desc())
    all_assets = list(db.scalars(stmt).all())

    # Group by (scene_id or scene_group_id, stage_key, original_name) and keep max version
    groups: dict[tuple, Asset] = {}
    for a in all_assets:
        key = (
            a.scene_id if a.scene_id is not None else a.scene_group_id,
            a.stage_key,
            a.asset_type,
            a.original_name,
        )
        if key not in groups or a.version > groups[key].version:
            groups[key] = a

    return sorted(groups.values(), key=lambda item: item.id, reverse=True)


@router.get("/{asset_id}/versions", response_model=list[AssetRead])
def list_asset_versions(
    asset_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> list[Asset]:
    """Return all versions of the same asset group."""
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    require_project_access(asset.project_id, current_user, db)

    if asset.scene_id is not None:
        stmt = (
            select(Asset)
            .options(selectinload(Asset.attachments))
            .where(
                Asset.scene_id == asset.scene_id,
                Asset.stage_key == asset.stage_key,
                Asset.asset_type == asset.asset_type,
                Asset.original_name == asset.original_name,
            )
            .order_by(Asset.version.asc())
        )
    else:
        stmt = (
            select(Asset)
            .options(selectinload(Asset.attachments))
            .where(
                Asset.scene_group_id == asset.scene_group_id,
                Asset.stage_key == asset.stage_key,
                Asset.asset_type == asset.asset_type,
                Asset.original_name == asset.original_name,
            )
            .order_by(Asset.version.asc())
        )
    return list(db.scalars(stmt).all())


@router.post("", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
def create_asset(
    payload: AssetCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Asset:
    require_project_access(payload.project_id, current_user, db)
    group_filter = [
        Asset.project_id == payload.project_id,
        Asset.scene_id == payload.scene_id,
        Asset.scene_group_id == payload.scene_group_id,
        Asset.stage_key == payload.stage_key,
        Asset.asset_type == payload.asset_type,
        Asset.original_name == payload.original_name,
    ]
    next_version = (db.scalar(select(func.max(Asset.version)).where(*group_filter)) or 0) + 1
    asset = Asset(
        project_id=payload.project_id,
        scene_group_id=payload.scene_group_id,
        scene_id=payload.scene_id,
        stage_key=payload.stage_key,
        asset_type=payload.asset_type,
        media_type=payload.media_type,
        is_global=payload.is_global,
        filename=payload.original_name,
        original_name=payload.original_name,
        storage_path="",
        version=next_version,
        note=payload.note,
        metadata_json=payload.metadata_json,
        uploaded_by=current_user.id,
    )
    db.add(asset)
    db.commit()
    stmt = select(Asset).options(selectinload(Asset.attachments)).where(Asset.id == asset.id)
    return db.scalar(stmt)


@router.get("/{asset_id}", response_model=AssetRead)
def get_asset(
    asset_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Asset:
    stmt = select(Asset).options(selectinload(Asset.attachments)).where(Asset.id == asset_id)
    asset = db.scalar(stmt)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    require_project_access(asset.project_id, current_user, db)
    return asset


@router.put("/{asset_id}", response_model=AssetRead)
def update_asset(
    asset_id: int,
    payload: AssetUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Asset:
    stmt = select(Asset).options(selectinload(Asset.attachments)).where(Asset.id == asset_id)
    asset = db.scalar(stmt)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    require_project_access(asset.project_id, current_user, db)
    if payload.note is not None:
        asset.note = payload.note
    if payload.is_global is not None:
        asset.is_global = payload.is_global
    db.commit()
    db.refresh(asset)
    return asset


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    asset_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    require_project_access(asset.project_id, current_user, db)
    db.delete(asset)
    db.commit()


# Asset attachments metadata endpoint

class AttachmentCreatePayload(BaseModel):
    filename: str
    media_type: str = "binary"
    public_url: str
    size_bytes: int | None = None
    metadata_json: dict | None = None


@router.post("/{asset_id}/attachments", response_model=dict)
def create_asset_attachment_meta(
    asset_id: int,
    payload: AttachmentCreatePayload,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    """Create an attachment record (metadata only; file upload is via /upload)."""
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    require_project_access(asset.project_id, current_user, db)
    attachment = AssetAttachment(
        asset_id=asset_id,
        filename=payload.filename,
        media_type=payload.media_type,
        storage_path="",
        public_url=payload.public_url,
        size_bytes=payload.size_bytes,
        metadata_json=payload.metadata_json,
        uploaded_by=current_user.id,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return {"attachment_id": attachment.id, "asset_id": asset_id, "filename": attachment.filename}

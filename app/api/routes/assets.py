from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

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
    db: Session = Depends(get_db),
) -> list[Asset]:
    stmt = select(Asset).order_by(Asset.id.desc())
    if project_id is not None:
        stmt = stmt.where(Asset.project_id == project_id)
    if scene_id is not None:
        stmt = stmt.where(Asset.scene_id == scene_id)
    if scene_group_id is not None:
        stmt = stmt.where(Asset.scene_group_id == scene_group_id)
    if stage_key is not None:
        stmt = stmt.where(Asset.stage_key == stage_key)
    if is_global is not None:
        stmt = stmt.where(Asset.is_global == is_global)
    return list(db.scalars(stmt).all())


@router.post("", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
def create_asset(payload: AssetCreate, db: Session = Depends(get_db)) -> Asset:
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
        version=1,
        note=payload.note,
        metadata_json=payload.metadata_json,
        uploaded_by=1,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.get("/{asset_id}", response_model=AssetRead)
def get_asset(asset_id: int, db: Session = Depends(get_db)) -> Asset:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    return asset


@router.put("/{asset_id}", response_model=AssetRead)
def update_asset(asset_id: int, payload: AssetUpdate, db: Session = Depends(get_db)) -> Asset:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    if payload.note is not None:
        asset.note = payload.note
    if payload.is_global is not None:
        asset.is_global = payload.is_global
    db.commit()
    db.refresh(asset)
    return asset


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(asset_id: int, db: Session = Depends(get_db)) -> None:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")
    db.delete(asset)
    db.commit()

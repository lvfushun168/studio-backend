import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_project_access
from app.core.config import settings
from app.core.database import get_db
from app.models.asset import Asset, AssetAttachment

router = APIRouter()


def _save_uploaded_file(upload_file: UploadFile, subdir: str) -> tuple[str, str]:
    """保存上传文件到存储目录，返回 (storage_path, public_url)。"""
    ext = Path(upload_file.filename or "file.bin").suffix
    safe_name = f"{uuid.uuid4().hex}{ext}"
    dest_dir = settings.media_root_path / subdir
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest_path = dest_dir / safe_name
    content = upload_file.file.read()
    dest_path.write_bytes(content)
    storage_path = str(dest_path.relative_to(settings.media_root_path))
    public_url = f"/media/{storage_path}"
    return storage_path, public_url


def _detect_media_type(filename: str | None) -> str:
    ext = Path(filename or "").suffix.lstrip(".").lower()
    if ext in ("jpg", "jpeg", "png", "gif", "webp", "bmp"):
        return "image"
    elif ext in ("mp4", "webm", "mov"):
        return "video"
    return "binary"


@router.post("/assets/{asset_id}/file", response_model=dict)
def upload_asset_file(
    asset_id: int,
    file: UploadFile = File(...),
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> dict:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    require_project_access(asset.project_id, current_user, db)

    original_name = file.filename or asset.original_name
    ext = Path(original_name).suffix.lstrip(".").lower()

    # Check if we should create a new version
    # Version grouping: scene_id + stage_key + original_name (or scene_group_id + original_name for global)
    if asset.scene_id is not None:
        group_filter = (
            Asset.scene_id == asset.scene_id,
            Asset.stage_key == asset.stage_key,
            Asset.original_name == original_name,
        )
    else:
        group_filter = (
            Asset.scene_group_id == asset.scene_group_id,
            Asset.stage_key == asset.stage_key,
            Asset.original_name == original_name,
        )

    max_version = db.scalar(
        select(func.max(Asset.version)).where(*group_filter)
    ) or 0

    subdir = f"projects/{asset.project_id}/assets"
    storage_path, public_url = _save_uploaded_file(file, subdir)

    # If this is the first upload or original_name changed, update existing asset
    if not asset.storage_path or asset.original_name != original_name:
        asset.filename = file.filename or asset.filename
        asset.original_name = original_name
        asset.storage_path = storage_path
        asset.public_url = public_url
        asset.extension = ext if ext else None
        asset.media_type = _detect_media_type(original_name)
        asset.version = max(1, max_version)
        asset.uploaded_by = current_user.id
        db.commit()
        db.refresh(asset)
        return {
            "asset_id": asset.id,
            "version": asset.version,
            "storage_path": storage_path,
            "public_url": public_url,
        }

    # Same name upload: create new version
    new_asset = Asset(
        project_id=asset.project_id,
        scene_group_id=asset.scene_group_id,
        scene_id=asset.scene_id,
        stage_key=asset.stage_key,
        asset_type=asset.asset_type,
        media_type=_detect_media_type(original_name),
        bank_material_id=asset.bank_material_id,
        bank_reference_id=asset.bank_reference_id,
        is_global=asset.is_global,
        filename=file.filename or asset.filename,
        original_name=original_name,
        extension=ext if ext else None,
        storage_path=storage_path,
        public_url=public_url,
        version=max_version + 1,
        note=asset.note,
        metadata_json=asset.metadata_json,
        uploaded_by=current_user.id,
    )
    db.add(new_asset)
    db.commit()
    db.refresh(new_asset)
    return {
        "asset_id": new_asset.id,
        "version": new_asset.version,
        "storage_path": storage_path,
        "public_url": public_url,
    }


@router.post("/assets/{asset_id}/attachments", response_model=dict)
def upload_asset_attachment(
    asset_id: int,
    file: UploadFile = File(...),
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> dict:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    require_project_access(asset.project_id, current_user, db)

    subdir = f"projects/{asset.project_id}/attachments"
    storage_path, public_url = _save_uploaded_file(file, subdir)

    media_type = _detect_media_type(file.filename)

    attachment = AssetAttachment(
        asset_id=asset_id,
        filename=file.filename or "attachment",
        media_type=media_type,
        storage_path=storage_path,
        public_url=public_url,
        uploaded_by=current_user.id,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return {"attachment_id": attachment.id, "storage_path": storage_path, "public_url": public_url}

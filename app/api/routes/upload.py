import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.orm import Session

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


@router.post("/assets/{asset_id}/file", response_model=dict)
def upload_asset_file(
    asset_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    subdir = f"projects/{asset.project_id}/assets"
    storage_path, public_url = _save_uploaded_file(file, subdir)

    asset.filename = file.filename or asset.filename
    asset.original_name = file.filename or asset.original_name
    asset.storage_path = storage_path
    asset.public_url = public_url
    ext = Path(file.filename or "").suffix.lstrip(".").lower()
    asset.extension = ext if ext else None
    if ext in ("jpg", "jpeg", "png", "gif", "webp", "bmp"):
        asset.media_type = "image"
    elif ext in ("mp4", "webm", "mov"):
        asset.media_type = "video"
    else:
        asset.media_type = "binary"

    db.commit()
    db.refresh(asset)
    return {"asset_id": asset.id, "storage_path": storage_path, "public_url": public_url}


@router.post("/assets/{asset_id}/attachments", response_model=dict)
def upload_asset_attachment(
    asset_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> dict:
    asset = db.get(Asset, asset_id)
    if not asset:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset not found")

    subdir = f"projects/{asset.project_id}/attachments"
    storage_path, public_url = _save_uploaded_file(file, subdir)

    ext = Path(file.filename or "").suffix.lstrip(".").lower()
    media_type = "binary"
    if ext in ("jpg", "jpeg", "png", "gif", "webp", "bmp"):
        media_type = "image"
    elif ext in ("mp4", "webm", "mov"):
        media_type = "video"

    attachment = AssetAttachment(
        asset_id=asset_id,
        filename=file.filename or "attachment",
        media_type=media_type,
        storage_path=storage_path,
        public_url=public_url,
        uploaded_by=1,
    )
    db.add(attachment)
    db.commit()
    db.refresh(attachment)
    return {"attachment_id": attachment.id, "storage_path": storage_path, "public_url": public_url}

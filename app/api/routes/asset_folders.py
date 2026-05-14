from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, PRODUCER_ROLES, get_accessible_project_ids, require_project_access, require_role
from app.core.database import get_db
from app.models.asset import Asset, AssetFolder
from app.schemas.asset_folder import AssetFolderCreate, AssetFolderRead, AssetFolderUpdate

router = APIRouter()


@router.get("", response_model=list[AssetFolderRead])
def list_asset_folders(
    project_id: int | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[AssetFolder]:
    stmt = select(AssetFolder).order_by(AssetFolder.parent_id.asc().nulls_first(), AssetFolder.name.asc(), AssetFolder.id.asc())
    if project_id is not None:
        require_project_access(project_id, current_user, db)
        stmt = stmt.where(AssetFolder.project_id == project_id)
    elif current_user.role != "admin":
        accessible_project_ids = get_accessible_project_ids(current_user, db)
        if not accessible_project_ids:
            return []
        stmt = stmt.where(AssetFolder.project_id.in_(accessible_project_ids))
    return list(db.scalars(stmt).all())


@router.post("", response_model=AssetFolderRead, status_code=status.HTTP_201_CREATED)
def create_asset_folder(
    payload: AssetFolderCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> AssetFolder:
    require_role(PRODUCER_ROLES)(current_user)
    require_project_access(payload.project_id, current_user, db)

    if payload.parent_id is not None:
        parent = db.get(AssetFolder, payload.parent_id)
        if not parent or parent.project_id != payload.project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent folder not found in project")
    duplicate = db.scalar(
        select(AssetFolder).where(
            AssetFolder.project_id == payload.project_id,
            AssetFolder.parent_id == payload.parent_id,
            func.lower(AssetFolder.name) == payload.name.strip().lower(),
        )
    )
    if duplicate:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Folder name already exists under the same parent")

    folder = AssetFolder(
        project_id=payload.project_id,
        parent_id=payload.parent_id,
        name=payload.name.strip(),
        created_by=current_user.id,
    )
    db.add(folder)
    db.commit()
    db.refresh(folder)
    return folder


@router.put("/{folder_id}", response_model=AssetFolderRead)
def update_asset_folder(
    folder_id: int,
    payload: AssetFolderUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> AssetFolder:
    require_role(PRODUCER_ROLES)(current_user)
    folder = db.get(AssetFolder, folder_id)
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset folder not found")
    require_project_access(folder.project_id, current_user, db)

    next_parent_id = folder.parent_id if "parent_id" not in payload.model_fields_set else payload.parent_id
    if next_parent_id == folder.id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Folder cannot be moved into itself")
    if "parent_id" in payload.model_fields_set and payload.parent_id is not None:
        parent = db.get(AssetFolder, payload.parent_id)
        if not parent or parent.project_id != folder.project_id:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Parent folder not found in project")
        cursor = parent
        while cursor is not None:
            if cursor.id == folder.id:
                raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Folder cannot be moved into its descendant")
            cursor = db.get(AssetFolder, cursor.parent_id) if cursor.parent_id is not None else None

    next_name = folder.name if payload.name is None else payload.name.strip()
    duplicate = db.scalar(
        select(AssetFolder).where(
            AssetFolder.project_id == folder.project_id,
            AssetFolder.parent_id == next_parent_id,
            func.lower(AssetFolder.name) == next_name.lower(),
            AssetFolder.id != folder.id,
        )
    )
    if duplicate:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Folder name already exists under the same parent")

    if payload.name is not None:
        folder.name = next_name
    if "parent_id" in payload.model_fields_set:
        folder.parent_id = payload.parent_id
    db.commit()
    db.refresh(folder)
    return folder


@router.delete("/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset_folder(
    folder_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    require_role(PRODUCER_ROLES)(current_user)
    folder = db.get(AssetFolder, folder_id)
    if not folder:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Asset folder not found")
    require_project_access(folder.project_id, current_user, db)

    child_exists = db.scalar(select(AssetFolder.id).where(AssetFolder.parent_id == folder.id).limit(1))
    if child_exists is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Folder has child folders and cannot be deleted")
    asset_exists = db.scalar(select(Asset.id).where(Asset.folder_id == folder.id).limit(1))
    if asset_exists is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Folder still contains assets and cannot be deleted")

    db.delete(folder)
    db.commit()

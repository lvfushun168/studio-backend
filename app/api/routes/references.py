from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, get_accessible_project_ids, require_project_access
from app.core.database import get_db
from app.models.reference import Reference
from app.schemas.reference import ReferenceCreate, ReferenceRead

router = APIRouter()


def _validate_reference_object(
    db: Session,
    *,
    project_id: int,
    object_type: str,
    object_id: int,
) -> bool:
    model_map = {
        "asset": ("app.models.asset", "Asset"),
        "annotation": ("app.models.annotation", "Annotation"),
        "scene": ("app.models.scene", "Scene"),
        "scene_group": ("app.models.project", "SceneGroup"),
        "project": ("app.models.project", "Project"),
        "bank_material": ("app.models.bank", "BankMaterial"),
        "bank_reference": ("app.models.bank", "BankReference"),
    }
    module_name, class_name = model_map.get(object_type, (None, None))
    if not module_name:
        return False
    module = __import__(module_name, fromlist=[class_name])
    model_cls = getattr(module, class_name)
    obj = db.get(model_cls, object_id)
    if not obj:
        return False
    if object_type == "project":
        return obj.id == project_id
    return getattr(obj, "project_id", project_id) == project_id


@router.get("", response_model=list[ReferenceRead])
def list_references(
    project_id: int | None = None,
    source_type: str | None = None,
    source_id: int | None = None,
    target_type: str | None = None,
    target_id: int | None = None,
    relation_type: str | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[Reference]:
    stmt = select(Reference).order_by(Reference.id.desc())
    if project_id is not None:
        require_project_access(project_id, current_user, db)
        stmt = stmt.where(Reference.project_id == project_id)
    elif current_user.role != "admin":
        accessible_project_ids = get_accessible_project_ids(current_user, db)
        if not accessible_project_ids:
            return []
        stmt = stmt.where(Reference.project_id.in_(accessible_project_ids))
    if source_type is not None:
        stmt = stmt.where(Reference.source_type == source_type)
    if source_id is not None:
        stmt = stmt.where(Reference.source_id == source_id)
    if target_type is not None:
        stmt = stmt.where(Reference.target_type == target_type)
    if target_id is not None:
        stmt = stmt.where(Reference.target_id == target_id)
    if relation_type is not None:
        stmt = stmt.where(Reference.relation_type == relation_type)
    return list(db.scalars(stmt).all())


@router.post("", response_model=ReferenceRead, status_code=status.HTTP_201_CREATED)
def create_reference(
    payload: ReferenceCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> Reference:
    require_project_access(payload.project_id, current_user, db)
    if not _validate_reference_object(db, project_id=payload.project_id, object_type=payload.source_type, object_id=payload.source_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid source object")
    if not _validate_reference_object(db, project_id=payload.project_id, object_type=payload.target_type, object_id=payload.target_id):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid target object")
    duplicate_stmt = select(Reference).where(
        Reference.project_id == payload.project_id,
        Reference.source_type == payload.source_type,
        Reference.source_id == payload.source_id,
        Reference.target_type == payload.target_type,
        Reference.target_id == payload.target_id,
        Reference.relation_type == payload.relation_type,
    )
    if db.scalar(duplicate_stmt):
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Reference already exists")
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


@router.get("/summary/by-object")
def summarize_references_by_object(
    project_id: int,
    object_type: str,
    object_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    require_project_access(project_id, current_user, db)
    outgoing = db.scalar(
        select(func.count(Reference.id)).where(
            Reference.project_id == project_id,
            Reference.source_type == object_type,
            Reference.source_id == object_id,
        )
    ) or 0
    incoming = db.scalar(
        select(func.count(Reference.id)).where(
            Reference.project_id == project_id,
            Reference.target_type == object_type,
            Reference.target_id == object_id,
        )
    ) or 0
    return {
        "projectId": project_id,
        "objectType": object_type,
        "objectId": object_id,
        "outgoingCount": outgoing,
        "incomingCount": incoming,
    }


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

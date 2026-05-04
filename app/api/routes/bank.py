from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import (
    CurrentUser,
    DIRECTOR_PRODUCER_ROLES,
    get_accessible_project_ids,
    require_project_access,
    require_role,
)
from app.core.database import get_db
from app.models.bank import BankMaterial, BankReference
from app.schemas.bank import (
    BankMaterialCreate,
    BankMaterialRead,
    BankMaterialUpdate,
    BankReferenceCreate,
    BankReferenceDetach,
    BankReferenceRead,
)
from app.services.bank_service import (
    create_bank_material_from_asset,
    create_bank_reference_with_asset,
    detach_bank_reference_with_asset,
)

router = APIRouter()


# ---- BankMaterial ----

@router.get("/materials", response_model=list[BankMaterialRead])
def list_bank_materials(
    project_id: int | None = None,
    character_name: str | None = None,
    part_name: str | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[BankMaterial]:
    stmt = select(BankMaterial).order_by(BankMaterial.id.desc())
    if project_id is not None:
        require_project_access(project_id, current_user, db)
        stmt = stmt.where(BankMaterial.project_id == project_id)
    elif current_user.role != "admin":
        accessible_project_ids = get_accessible_project_ids(current_user, db)
        if not accessible_project_ids:
            return []
        stmt = stmt.where(BankMaterial.project_id.in_(accessible_project_ids))
    if character_name is not None:
        stmt = stmt.where(BankMaterial.character_name == character_name)
    if part_name is not None:
        stmt = stmt.where(BankMaterial.part_name == part_name)
    return list(db.scalars(stmt).all())


@router.post("/materials", response_model=BankMaterialRead, status_code=status.HTTP_201_CREATED)
def create_bank_material(
    payload: BankMaterialCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> BankMaterial:
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    require_project_access(payload.project_id, current_user, db)
    source_asset_id = payload.source_asset_id
    if source_asset_id is None:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="source_asset_id is required")
    try:
        material = create_bank_material_from_asset(
            db,
            project_id=payload.project_id,
            source_asset_id=source_asset_id,
            created_by=current_user.id,
            name=payload.name,
            character_name=payload.character_name,
            part_name=payload.part_name,
            pose=payload.pose,
            angle=payload.angle,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    db.add(material)
    db.commit()
    db.refresh(material)
    return material


@router.get("/materials/{material_id}", response_model=BankMaterialRead)
def get_bank_material(
    material_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> BankMaterial:
    material = db.get(BankMaterial, material_id)
    if not material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BankMaterial not found")
    require_project_access(material.project_id, current_user, db)
    return material


@router.put("/materials/{material_id}", response_model=BankMaterialRead)
def update_bank_material(
    material_id: int,
    payload: BankMaterialUpdate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> BankMaterial:
    material = db.get(BankMaterial, material_id)
    if not material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BankMaterial not found")
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    require_project_access(material.project_id, current_user, db)

    if payload.name is not None:
        material.name = payload.name
    if payload.character_name is not None:
        material.character_name = payload.character_name
    if payload.part_name is not None:
        material.part_name = payload.part_name
    if payload.pose is not None:
        material.pose = payload.pose
    if payload.angle is not None:
        material.angle = payload.angle
    if payload.status is not None:
        material.status = payload.status

    db.add(material)
    db.commit()
    db.refresh(material)
    return material


@router.delete("/materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bank_material(
    material_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    material = db.get(BankMaterial, material_id)
    if not material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BankMaterial not found")
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    require_project_access(material.project_id, current_user, db)
    ref_stmt = select(BankReference).where(BankReference.bank_material_id == material_id)
    if db.scalar(ref_stmt):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Cannot delete bank material with reference history")
    db.delete(material)
    db.commit()


# ---- BankReference ----

@router.get("/references", response_model=list[BankReferenceRead])
def list_bank_references(
    scene_id: int | None = None,
    bank_material_id: int | None = None,
    current_user: CurrentUser = None,
    db: Session = Depends(get_db),
) -> list[BankReference]:
    stmt = select(BankReference).order_by(BankReference.id.desc())
    if current_user.role != "admin":
        accessible_project_ids = get_accessible_project_ids(current_user, db)
        if not accessible_project_ids:
            return []
        stmt = stmt.where(BankReference.project_id.in_(accessible_project_ids))
    if scene_id is not None:
        stmt = stmt.where(BankReference.scene_id == scene_id)
    if bank_material_id is not None:
        stmt = stmt.where(BankReference.bank_material_id == bank_material_id)
    return list(db.scalars(stmt).all())


@router.post("/references", response_model=BankReferenceRead, status_code=status.HTTP_201_CREATED)
def create_bank_reference(
    payload: BankReferenceCreate,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> BankReference:
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    require_project_access(payload.project_id, current_user, db)
    material = db.get(BankMaterial, payload.bank_material_id)
    if not material or material.project_id != payload.project_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BankMaterial not found in project")
    try:
        ref, _derived_asset = create_bank_reference_with_asset(
            db,
            material=material,
            project_id=payload.project_id,
            scene_id=payload.scene_id,
            stage_key=payload.stage_key,
            version=payload.version,
            created_by=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    db.commit()
    db.refresh(ref)
    return ref


@router.get("/references/{reference_id}", response_model=BankReferenceRead)
def get_bank_reference(
    reference_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> BankReference:
    ref = db.get(BankReference, reference_id)
    if not ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BankReference not found")
    require_project_access(ref.project_id, current_user, db)
    return ref


@router.delete("/references/{reference_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bank_reference(
    reference_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> None:
    ref = db.get(BankReference, reference_id)
    if not ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BankReference not found")
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    require_project_access(ref.project_id, current_user, db)
    material = db.get(BankMaterial, ref.bank_material_id)
    if material and material.ref_count > 0 and ref.status == "active":
        material.ref_count -= 1
    db.delete(ref)
    db.commit()


@router.post("/references/{reference_id}/detach", response_model=BankReferenceRead)
def detach_bank_reference(
    reference_id: int,
    payload: BankReferenceDetach,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> BankReference:
    ref = db.get(BankReference, reference_id)
    if not ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BankReference not found")
    require_role(DIRECTOR_PRODUCER_ROLES)(current_user)
    require_project_access(ref.project_id, current_user, db)
    try:
        ref, _detached_asset = detach_bank_reference_with_asset(
            db,
            reference=ref,
            detached_asset_id=payload.detached_asset_id,
            detached_by=current_user.id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc))
    db.commit()
    db.refresh(ref)
    return ref

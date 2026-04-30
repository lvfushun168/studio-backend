from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.bank import BankMaterial, BankReference
from app.schemas.bank import BankMaterialCreate, BankMaterialRead, BankReferenceCreate, BankReferenceRead

router = APIRouter()


# ---- BankMaterial ----

@router.get("/materials", response_model=list[BankMaterialRead])
def list_bank_materials(
    project_id: int | None = None,
    character_name: str | None = None,
    part_name: str | None = None,
    db: Session = Depends(get_db),
) -> list[BankMaterial]:
    stmt = select(BankMaterial).order_by(BankMaterial.id.desc())
    if project_id is not None:
        stmt = stmt.where(BankMaterial.project_id == project_id)
    if character_name is not None:
        stmt = stmt.where(BankMaterial.character_name == character_name)
    if part_name is not None:
        stmt = stmt.where(BankMaterial.part_name == part_name)
    return list(db.scalars(stmt).all())


@router.post("/materials", response_model=BankMaterialRead, status_code=status.HTTP_201_CREATED)
def create_bank_material(payload: BankMaterialCreate, db: Session = Depends(get_db)) -> BankMaterial:
    material = BankMaterial(
        project_id=payload.project_id,
        source_asset_id=payload.source_asset_id,
        source_scene_id=payload.source_scene_id,
        source_stage_key=payload.source_stage_key,
        name=payload.name,
        character_name=payload.character_name,
        part_name=payload.part_name,
        pose=payload.pose,
        angle=payload.angle,
        current_version=1,
        created_by=1,
    )
    db.add(material)
    db.commit()
    db.refresh(material)
    return material


@router.get("/materials/{material_id}", response_model=BankMaterialRead)
def get_bank_material(material_id: int, db: Session = Depends(get_db)) -> BankMaterial:
    material = db.get(BankMaterial, material_id)
    if not material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BankMaterial not found")
    return material


@router.delete("/materials/{material_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bank_material(material_id: int, db: Session = Depends(get_db)) -> None:
    material = db.get(BankMaterial, material_id)
    if not material:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BankMaterial not found")
    db.delete(material)
    db.commit()


# ---- BankReference ----

@router.get("/references", response_model=list[BankReferenceRead])
def list_bank_references(
    scene_id: int | None = None,
    bank_material_id: int | None = None,
    db: Session = Depends(get_db),
) -> list[BankReference]:
    stmt = select(BankReference).order_by(BankReference.id.desc())
    if scene_id is not None:
        stmt = stmt.where(BankReference.scene_id == scene_id)
    if bank_material_id is not None:
        stmt = stmt.where(BankReference.bank_material_id == bank_material_id)
    return list(db.scalars(stmt).all())


@router.post("/references", response_model=BankReferenceRead, status_code=status.HTTP_201_CREATED)
def create_bank_reference(payload: BankReferenceCreate, db: Session = Depends(get_db)) -> BankReference:
    ref = BankReference(
        bank_material_id=payload.bank_material_id,
        project_id=payload.project_id,
        scene_id=payload.scene_id,
        stage_key=payload.stage_key,
        version=payload.version,
        status="active",
        created_by=1,
    )
    db.add(ref)
    db.commit()
    db.refresh(ref)
    return ref


@router.get("/references/{reference_id}", response_model=BankReferenceRead)
def get_bank_reference(reference_id: int, db: Session = Depends(get_db)) -> BankReference:
    ref = db.get(BankReference, reference_id)
    if not ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BankReference not found")
    return ref


@router.delete("/references/{reference_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_bank_reference(reference_id: int, db: Session = Depends(get_db)) -> None:
    ref = db.get(BankReference, reference_id)
    if not ref:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="BankReference not found")
    db.delete(ref)
    db.commit()

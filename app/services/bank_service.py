from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.asset import Asset
from app.models.bank import BankMaterial, BankReference
from app.models.scene import Scene


def create_bank_material_from_asset(
    db: Session,
    *,
    project_id: int,
    source_asset_id: int,
    created_by: int,
    name: str,
    character_name: str | None = None,
    part_name: str | None = None,
    pose: str | None = None,
    angle: str | None = None,
) -> BankMaterial:
    source_asset = db.get(Asset, source_asset_id)
    if not source_asset or source_asset.project_id != project_id:
        raise ValueError("Source asset not found in project")

    if source_asset.scene_id is None:
        raise ValueError("Only scene assets can be published to bank")

    material = BankMaterial(
        project_id=project_id,
        source_asset_id=source_asset.id,
        source_scene_id=source_asset.scene_id,
        source_stage_key=source_asset.stage_key,
        name=name,
        character_name=character_name,
        part_name=part_name,
        pose=pose,
        angle=angle,
        current_asset_id=source_asset.id,
        current_version=source_asset.version,
        ref_count=0,
        status="active",
        metadata_json={
            "mediaType": source_asset.media_type,
            "thumbnailUrl": source_asset.thumbnail_url,
            "publicUrl": source_asset.public_url,
        },
        created_by=created_by,
    )
    db.add(material)
    db.flush()
    return material


def _clone_asset_for_bank_reference(
    *,
    source_asset: Asset,
    project_id: int,
    scene_id: int,
    scene_group_id: int,
    stage_key: str,
    bank_material_id: int,
    bank_reference_id: int | None,
    uploaded_by: int,
    original_name_suffix: str = "",
    note_prefix: str = "Bank reference",
) -> Asset:
    suffix = f"_{original_name_suffix}" if original_name_suffix else ""
    return Asset(
        project_id=project_id,
        scene_group_id=scene_group_id,
        scene_id=scene_id,
        stage_key=stage_key,
        asset_type="bank_reference",
        media_type=source_asset.media_type,
        bank_material_id=bank_material_id,
        bank_reference_id=bank_reference_id,
        is_global=False,
        filename=source_asset.filename,
        original_name=f"{source_asset.original_name.rsplit('.', 1)[0]}{suffix}.{source_asset.extension}" if source_asset.extension else f"{source_asset.original_name}{suffix}",
        extension=source_asset.extension,
        storage_path=source_asset.storage_path,
        public_url=source_asset.public_url,
        thumbnail_path=source_asset.thumbnail_path,
        thumbnail_url=source_asset.thumbnail_url,
        version=1,
        note=f"{note_prefix} from material #{bank_material_id}",
        metadata_json=dict(source_asset.metadata_json or {}),
        uploaded_by=uploaded_by,
    )


def create_bank_reference_with_asset(
    db: Session,
    *,
    material: BankMaterial,
    project_id: int,
    scene_id: int,
    stage_key: str,
    version: int | None,
    created_by: int,
) -> tuple[BankReference, Asset]:
    scene = db.get(Scene, scene_id)
    if not scene or scene.project_id != project_id:
        raise ValueError("Scene not found in project")
    if material.project_id != project_id:
        raise ValueError("Bank material not found in project")
    if material.status != "active":
        raise ValueError("Bank material is not active")

    source_asset = db.get(Asset, material.current_asset_id or material.source_asset_id)
    if not source_asset:
        raise ValueError("Source asset for bank material not found")

    existing_stmt = select(BankReference).where(
        BankReference.bank_material_id == material.id,
        BankReference.scene_id == scene_id,
        BankReference.stage_key == stage_key,
        BankReference.status == "active",
    )
    if db.scalar(existing_stmt):
        raise ValueError("Active bank reference already exists for this scene and stage")

    reference = BankReference(
        bank_material_id=material.id,
        project_id=project_id,
        scene_id=scene_id,
        stage_key=stage_key,
        version=version or material.current_version,
        status="active",
        created_by=created_by,
    )
    db.add(reference)
    db.flush()

    derived_asset = _clone_asset_for_bank_reference(
        source_asset=source_asset,
        project_id=project_id,
        scene_id=scene_id,
        scene_group_id=scene.scene_group_id,
        stage_key=stage_key,
        bank_material_id=material.id,
        bank_reference_id=reference.id,
        uploaded_by=created_by,
        original_name_suffix=f"bankref_{reference.id}",
    )
    db.add(derived_asset)
    db.flush()

    reference.detached_asset_id = None
    material.ref_count += 1
    return reference, derived_asset


def detach_bank_reference_with_asset(
    db: Session,
    *,
    reference: BankReference,
    detached_asset_id: int | None,
    detached_by: int,
) -> tuple[BankReference, Asset | None]:
    if reference.status == "detached":
        return reference, db.get(Asset, reference.detached_asset_id) if reference.detached_asset_id else None

    material = db.get(BankMaterial, reference.bank_material_id)
    source_asset = None
    if detached_asset_id is not None:
        source_asset = db.get(Asset, detached_asset_id)
    else:
        source_stmt = select(Asset).where(
            Asset.bank_reference_id == reference.id,
            Asset.scene_id == reference.scene_id,
        ).order_by(Asset.id.desc())
        source_asset = db.scalar(source_stmt)
        if source_asset is None and material is not None:
            source_asset = db.get(Asset, material.current_asset_id or material.source_asset_id)

    detached_asset = None
    if source_asset is not None:
        scene = db.get(Scene, reference.scene_id)
        detached_asset = _clone_asset_for_bank_reference(
            source_asset=source_asset,
            project_id=reference.project_id,
            scene_id=reference.scene_id,
            scene_group_id=scene.scene_group_id if scene else source_asset.scene_group_id or 0,
            stage_key=reference.stage_key,
            bank_material_id=reference.bank_material_id,
            bank_reference_id=None,
            uploaded_by=detached_by,
            original_name_suffix=f"detached_{reference.id}",
            note_prefix="Detached bank reference",
        )
        db.add(detached_asset)
        db.flush()
        reference.detached_asset_id = detached_asset.id

    reference.status = "detached"
    if material and material.ref_count > 0:
        material.ref_count -= 1
    return reference, detached_asset

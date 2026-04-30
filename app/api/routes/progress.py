from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.auth import CurrentUser, require_project_access
from app.core.database import get_db
from app.models.scene import Scene, StageProgress
from app.models.project import Project

router = APIRouter()


@router.get("/projects/{project_id}")
def get_project_progress(
    project_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    require_project_access(project_id, current_user, db)

    scene_stmt = select(Scene).where(Scene.project_id == project_id)
    scenes = db.scalars(scene_stmt).all()
    scene_ids = [s.id for s in scenes]

    total_scenes = len(scenes)
    completed_scenes = 0
    stage_counts: dict[str, dict[str, int]] = {}

    if scene_ids:
        sp_stmt = select(StageProgress).where(StageProgress.scene_id.in_(scene_ids))
        progresses = db.scalars(sp_stmt).all()

        for sp in progresses:
            if sp.stage_key not in stage_counts:
                stage_counts[sp.stage_key] = {"approved": 0, "in_progress": 0, "reviewing": 0, "pending": 0, "locked": 0, "rejected": 0}
            if sp.status in stage_counts[sp.stage_key]:
                stage_counts[sp.stage_key][sp.status] += 1

        for s in scenes:
            final_sp = next((sp for sp in progresses if sp.scene_id == s.id and sp.stage_key == "final"), None)
            if final_sp and final_sp.status == "approved":
                completed_scenes += 1

    return {
        "projectId": project_id,
        "totalScenes": total_scenes,
        "completedScenes": completed_scenes,
        "stageCounts": stage_counts,
    }


@router.get("/projects/{project_id}/overview")
def get_project_overview(
    project_id: int,
    current_user: CurrentUser,
    db: Session = Depends(get_db),
) -> dict:
    project = db.get(Project, project_id)
    if not project:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Project not found")
    require_project_access(project_id, current_user, db)

    from app.models.asset import Asset
    from app.models.bank import BankMaterial, BankReference
    from app.models.annotation import Annotation

    total_scenes = db.scalar(select(func.count(Scene.id)).where(Scene.project_id == project_id)) or 0
    total_assets = db.scalar(select(func.count(Asset.id)).where(Asset.project_id == project_id)) or 0
    total_annotations = db.scalar(select(func.count(Annotation.id)).where(Annotation.project_id == project_id)) or 0
    total_bank_materials = db.scalar(select(func.count(BankMaterial.id)).where(BankMaterial.project_id == project_id)) or 0
    total_bank_references = db.scalar(select(func.count(BankReference.id)).where(BankReference.project_id == project_id)) or 0

    return {
        "projectId": project_id,
        "projectName": project.name,
        "totalScenes": total_scenes,
        "totalAssets": total_assets,
        "totalAnnotations": total_annotations,
        "totalBankMaterials": total_bank_materials,
        "totalBankReferences": total_bank_references,
    }

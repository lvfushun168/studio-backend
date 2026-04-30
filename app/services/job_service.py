from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.models.annotation import Annotation
from app.models.asset import Asset
from app.models.async_job import AsyncJob
from app.models.project import Project, SceneGroup
from app.models.scene import Scene
from app.services.media_service import generate_annotation_artifacts, generate_video_thumbnail


SUPPORTED_JOB_TYPES = {
    "annotation_render",
    "video_thumbnail",
    "project_export",
}


def enqueue_job(
    db: Session,
    *,
    job_type: str,
    payload_json: dict,
    created_by: int | None = None,
    project_id: int | None = None,
    priority: int = 100,
    max_retries: int = 3,
) -> AsyncJob:
    if job_type not in SUPPORTED_JOB_TYPES:
        raise ValueError(f"Unsupported job_type: {job_type}")
    job = AsyncJob(
        project_id=project_id,
        job_type=job_type,
        status="pending",
        priority=priority,
        payload_json=payload_json,
        result_json=None,
        retry_count=0,
        max_retries=max_retries,
        scheduled_at=datetime.now(timezone.utc),
        created_by=created_by,
    )
    db.add(job)
    db.flush()
    return job


def retry_job(db: Session, job: AsyncJob) -> AsyncJob:
    job.status = "pending"
    job.error_message = None
    job.started_at = None
    job.finished_at = None
    job.retry_count += 1
    db.flush()
    return job


def _project_export_path(project_id: int, job_id: int) -> Path:
    export_dir = settings.media_root_path / "exports" / str(project_id)
    export_dir.mkdir(parents=True, exist_ok=True)
    return export_dir / f"project_{project_id}_job_{job_id}.zip"


def build_project_export(db: Session, project_id: int, job_id: int) -> dict:
    project = db.get(Project, project_id)
    if not project:
        raise ValueError("Project not found")

    scenes = db.scalars(select(Scene).where(Scene.project_id == project_id).order_by(Scene.id.asc())).all()
    groups = db.scalars(select(SceneGroup).where(SceneGroup.project_id == project_id).order_by(SceneGroup.id.asc())).all()
    assets = db.scalars(select(Asset).where(Asset.project_id == project_id).order_by(Asset.id.asc())).all()
    annotations = db.scalars(select(Annotation).where(Annotation.project_id == project_id).order_by(Annotation.id.asc())).all()

    export_path = _project_export_path(project_id, job_id)
    manifest = {
        "project": {"id": project.id, "name": project.name, "status": project.status},
        "sceneGroups": [{"id": g.id, "name": g.name, "episodeId": g.episode_id} for g in groups],
        "scenes": [{"id": s.id, "name": s.name, "stageTemplate": s.stage_template, "pipeline": s.pipeline} for s in scenes],
        "assets": [
            {
                "id": a.id,
                "sceneId": a.scene_id,
                "sceneGroupId": a.scene_group_id,
                "stageKey": a.stage_key,
                "mediaType": a.media_type,
                "publicUrl": a.public_url,
                "storagePath": a.storage_path,
                "thumbnailUrl": a.thumbnail_url,
            }
            for a in assets
        ],
        "annotations": [
            {
                "id": anno.id,
                "targetAssetId": anno.target_asset_id,
                "frameNumber": anno.frame_number,
                "summary": anno.summary,
                "overlayUrl": anno.overlay_url,
                "mergedUrl": anno.merged_url,
            }
            for anno in annotations
        ],
    }

    with ZipFile(export_path, "w", compression=ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
        for asset in assets:
            if asset.storage_path:
                src = settings.media_root_path / asset.storage_path
                if src.is_file():
                    zf.write(src, f"assets/{asset.id}_{src.name}")
            if asset.thumbnail_path:
                thumb = settings.media_root_path / asset.thumbnail_path
                if thumb.is_file():
                    zf.write(thumb, f"thumbnails/{asset.id}_{thumb.name}")
        for anno in annotations:
            for path_value, folder in ((anno.overlay_path, "annotations"), (anno.merged_path, "annotations")):
                if path_value:
                    src = settings.media_root_path / path_value
                    if src.is_file():
                        zf.write(src, f"{folder}/{anno.id}_{src.name}")

    return {
        "exportPath": str(export_path),
        "exportUrl": f"/media/{export_path.relative_to(settings.media_root_path)}",
        "manifest": manifest,
    }


def handle_job(db: Session, job: AsyncJob) -> dict:
    payload = job.payload_json or {}
    if job.job_type == "annotation_render":
        annotation = db.get(Annotation, payload["annotation_id"])
        asset = db.get(Asset, annotation.target_asset_id) if annotation else None
        if not annotation or not asset:
            raise ValueError("Annotation or asset not found")
        result = generate_annotation_artifacts(annotation, asset)
        annotation.overlay_path = result["overlay_path"]
        annotation.overlay_url = result["overlay_url"]
        annotation.merged_path = result["merged_path"]
        annotation.merged_url = result["merged_url"]
        return result
    if job.job_type == "video_thumbnail":
        asset = db.get(Asset, payload["asset_id"])
        if not asset:
            raise ValueError("Asset not found")
        result = generate_video_thumbnail(asset)
        asset.thumbnail_path = result["thumbnail_path"]
        asset.thumbnail_url = result["thumbnail_url"]
        return result
    if job.job_type == "project_export":
        project_id = int(payload["project_id"])
        return build_project_export(db, project_id, job.id)
    raise ValueError(f"No handler for job type: {job.job_type}")

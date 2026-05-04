from __future__ import annotations

import importlib
import os
import subprocess
import sys
import uuid
import asyncio
import zipfile
from io import BytesIO
from pathlib import Path

import cv2
import numpy as np
import psycopg
import pytest
from fastapi.testclient import TestClient
from PIL import Image


ROOT_DIR = Path(__file__).resolve().parents[1]
ADMIN_DB_URL = "postgresql://lvfushun@127.0.0.1:5432/postgres"

if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))


@pytest.fixture(scope="session")
def test_database_url() -> str:
    db_name = f"studio_asset_test_{uuid.uuid4().hex[:8]}"
    with psycopg.connect(ADMIN_DB_URL, autocommit=True) as conn:
        conn.execute(f'CREATE DATABASE "{db_name}"')

    db_url = f"postgresql+psycopg://lvfushun@127.0.0.1:5432/{db_name}"
    env = {**os.environ, "DATABASE_URL": db_url}
    os.environ["DATABASE_URL"] = db_url

    subprocess.run(
        [str(ROOT_DIR / ".venv" / "bin" / "alembic"), "upgrade", "head"],
        cwd=ROOT_DIR,
        env=env,
        check=True,
    )
    subprocess.run(
        [str(ROOT_DIR / ".venv" / "bin" / "python"), "scripts/seed_data.py"],
        cwd=ROOT_DIR,
        env=env,
        check=True,
    )

    yield db_url

    with psycopg.connect(ADMIN_DB_URL, autocommit=True) as conn:
        conn.execute(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)')


@pytest.fixture()
def client(test_database_url: str) -> TestClient:
    importlib.invalidate_caches()
    from app.main import app

    return TestClient(app)


def test_projects_require_authentication(client: TestClient) -> None:
    response = client.get("/api/v1/projects")
    assert response.status_code == 401


def test_health_endpoint_reports_database_and_storage(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["database"]["ok"] is True
    assert payload["storage"]["ok"] is True


def test_assets_and_annotations_require_authentication(client: TestClient) -> None:
    asset_response = client.get("/api/v1/assets")
    annotation_response = client.get("/api/v1/annotations")

    assert asset_response.status_code == 401
    assert annotation_response.status_code == 401


def test_non_admin_cannot_list_all_users(client: TestClient) -> None:
    response = client.get("/api/v1/users", headers={"X-User-ID": "5"})
    assert response.status_code == 403


def test_non_admin_cannot_get_or_create_or_update_users(client: TestClient) -> None:
    headers = {"X-User-ID": "5"}

    get_response = client.get("/api/v1/users/1", headers=headers)
    create_response = client.post(
        "/api/v1/users",
        headers=headers,
        json={
            "username": "rogue",
            "display_name": "Rogue User",
            "email": "rogue@example.com",
            "role": "director",
            "is_active": True,
        },
    )
    update_response = client.put(
        "/api/v1/users/1",
        headers=headers,
        json={
            "username": "admin",
            "display_name": "系统管理员",
            "email": "admin@studio.com",
            "role": "artist",
            "is_active": True,
        },
    )

    assert get_response.status_code == 403
    assert create_response.status_code == 403
    assert update_response.status_code == 403


def test_project_creator_is_added_to_membership(client: TestClient) -> None:
    headers = {"X-User-ID": "4"}
    create_response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "name": "联调测试项目",
            "description": "smoke",
            "project_type": "single",
            "status": "active",
        },
    )
    assert create_response.status_code == 201
    project_id = create_response.json()["id"]

    list_response = client.get("/api/v1/projects", headers=headers)
    assert list_response.status_code == 200
    visible_project_ids = [item["id"] for item in list_response.json()]
    assert project_id in visible_project_ids


def test_project_with_audit_history_cannot_be_hard_deleted(client: TestClient) -> None:
    headers = {"X-User-ID": "4"}
    create_response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "name": "不可硬删项目",
            "description": "smoke",
            "project_type": "single",
            "status": "active",
        },
    )
    assert create_response.status_code == 201
    project_id = create_response.json()["id"]

    delete_response = client.delete(f"/api/v1/projects/{project_id}", headers=headers)
    assert delete_response.status_code == 409
    assert delete_response.json()["detail"] == "项目已有审计历史，不能直接删除，请改为归档"


def test_project_cover_can_be_uploaded(client: TestClient) -> None:
    headers = {"X-User-ID": "4"}
    create_response = client.post(
        "/api/v1/projects",
        headers=headers,
        json={
            "name": "封面项目",
            "description": "smoke",
            "project_type": "single",
            "status": "active",
        },
    )
    assert create_response.status_code == 201
    project_id = create_response.json()["id"]

    image_buffer = BytesIO()
    Image.new("RGB", (320, 240), (24, 120, 220)).save(image_buffer, format="PNG")
    upload_response = client.post(
        f"/api/v1/upload/projects/{project_id}/cover",
        headers=headers,
        files={"file": ("cover.png", image_buffer.getvalue(), "image/png")},
    )
    assert upload_response.status_code == 200
    assert upload_response.json()["cover_url"].startswith("/media/projects/")

    list_response = client.get("/api/v1/projects", headers=headers)
    assert list_response.status_code == 200
    project = next(item for item in list_response.json() if item["id"] == project_id)
    assert project["coverUrl"].startswith("/media/projects/")


def test_assets_are_scoped_to_project_membership(client: TestClient) -> None:
    response = client.get("/api/v1/assets", headers={"X-User-ID": "5"})
    assert response.status_code == 200
    payload = response.json()
    assert payload
    assert all(item["projectId"] == 1 for item in payload)


def test_role_boundaries_for_scene_and_workflow_operations(client: TestClient) -> None:
    visitor_create_scene = client.post(
        "/api/v1/scenes",
        headers={"X-User-ID": "8"},
        json={
            "project_id": 1,
            "scene_group_id": 1,
            "name": "VISITOR_SCENE",
            "level": "B",
            "stage_template": "ai_single_frame",
            "pipeline": "ai_single_frame",
        },
    )
    assert visitor_create_scene.status_code == 403

    producer_approve = client.post(
        "/api/v1/workflow/scenes/2/approve",
        headers={"X-User-ID": "4"},
        json={"stage_key": "ai_draw", "comment": "nope"},
    )
    assert producer_approve.status_code == 403

    visitor_submit = client.post(
        "/api/v1/workflow/scenes/1/submit",
        headers={"X-User-ID": "8"},
        json={"stage_key": "correction"},
    )
    assert visitor_submit.status_code == 403


def test_assets_and_annotations_are_scoped_to_project_membership(client: TestClient) -> None:
    asset_response = client.get("/api/v1/assets", headers={"X-User-ID": "6"})
    annotation_response = client.get("/api/v1/annotations", headers={"X-User-ID": "6"})

    assert asset_response.status_code == 200
    assert annotation_response.status_code == 200
    assert all(item["projectId"] == 1 or item["projectId"] == 2 for item in asset_response.json())
    assert all(item["projectId"] == 1 or item["projectId"] == 2 for item in annotation_response.json())

    forbidden_assets = client.get("/api/v1/assets", params={"project_id": 3}, headers={"X-User-ID": "6"})
    forbidden_annotations = client.get("/api/v1/annotations", params={"project_id": 3}, headers={"X-User-ID": "6"})
    assert forbidden_assets.status_code == 403
    assert forbidden_annotations.status_code == 403


def test_asset_latest_versions_and_attachments_are_returned(client: TestClient) -> None:
    response = client.get("/api/v1/assets/latest", params={"project_id": 1, "scene_id": 1}, headers={"X-User-ID": "2"})
    assert response.status_code == 200
    payload = response.json()

    ai_draw = next(item for item in payload if item["type"] == "ai_draw")
    assert ai_draw["version"] == 2
    assert ai_draw["originalName"] == "ai_result.jpg"
    assert len(ai_draw["attachments"]) == 1

    versions_response = client.get(f"/api/v1/assets/{ai_draw['id']}/versions", headers={"X-User-ID": "2"})
    assert versions_response.status_code == 200
    versions = versions_response.json()
    assert [item["version"] for item in versions] == [1, 2]


def test_uploading_same_asset_name_creates_new_version(client: TestClient) -> None:
    headers = {"X-User-ID": "5"}
    create_response = client.post(
        "/api/v1/assets",
        headers=headers,
        json={
            "project_id": 1,
            "scene_group_id": 1,
            "scene_id": 1,
            "stage_key": "correction",
            "asset_type": "original",
            "media_type": "image",
            "original_name": "same_name_version.png",
        },
    )
    assert create_response.status_code == 201
    asset = create_response.json()

    img1 = BytesIO()
    Image.new("RGB", (64, 64), (255, 0, 0)).save(img1, format="PNG")
    first_upload = client.post(
        f"/api/v1/upload/assets/{asset['id']}/file",
        headers=headers,
        files={"file": ("same_name_version.png", img1.getvalue(), "image/png")},
    )
    assert first_upload.status_code == 200
    assert first_upload.json()["version"] == 1

    img2 = BytesIO()
    Image.new("RGB", (64, 64), (0, 255, 0)).save(img2, format="PNG")
    second_upload = client.post(
        f"/api/v1/upload/assets/{asset['id']}/file",
        headers=headers,
        files={"file": ("same_name_version.png", img2.getvalue(), "image/png")},
    )
    assert second_upload.status_code == 200
    assert second_upload.json()["version"] == 2

    versions_response = client.get(f"/api/v1/assets/{second_upload.json()['asset_id']}/versions", headers=headers)
    assert versions_response.status_code == 200
    assert [item["version"] for item in versions_response.json()] == [1, 2]


def create_stage_asset(
    client: TestClient,
    headers: dict[str, str],
    *,
    project_id: int,
    scene_group_id: int,
    scene_id: int,
    stage_key: str,
    original_name: str | None = None,
) -> dict:
    response = client.post(
        "/api/v1/assets",
        headers=headers,
        json={
            "project_id": project_id,
            "scene_group_id": scene_group_id,
            "scene_id": scene_id,
            "stage_key": stage_key,
            "asset_type": "original",
            "media_type": "image",
            "original_name": original_name or f"{stage_key}_{scene_id}.png",
        },
    )
    assert response.status_code == 201
    return response.json()


def test_scene_matrix_returns_flattened_scenes_and_latest_assets(client: TestClient) -> None:
    response = client.get("/api/v1/scenes/matrix", params={"project_id": 1}, headers={"X-User-ID": "2"})
    assert response.status_code == 200
    payload = response.json()

    assert payload["projectId"] == 1
    assert payload["sceneGroups"]
    assert payload["scenes"]
    scene = next(item for item in payload["scenes"] if item["id"] == 1)
    assert scene["stageProgress"]["correction"]["status"] == "in_progress"
    assert scene["assignedUserIds"]
    assert scene["latestAssets"]["ai_draw"]["version"] == 2


def test_standard_storyboard_approval_unlocks_both_layout_branches(client: TestClient) -> None:
    director_headers = {"X-User-ID": "2"}
    artist_headers = {"X-User-ID": "5"}

    create_response = client.post(
        "/api/v1/scenes",
        headers=director_headers,
        json={
            "project_id": 1,
            "scene_group_id": 1,
            "name": "SC_STANDARD_UNLOCK",
            "level": "B",
            "stage_template": "standard",
            "pipeline": "standard",
        },
    )
    assert create_response.status_code == 201
    scene_id = create_response.json()["id"]

    create_stage_asset(
        client,
        artist_headers,
        project_id=1,
        scene_group_id=1,
        scene_id=scene_id,
        stage_key="storyboard",
        original_name="standard_unlock_storyboard.png",
    )

    submit_response = client.post(
        f"/api/v1/workflow/scenes/{scene_id}/submit",
        headers=artist_headers,
        json={"stage_key": "storyboard"},
    )
    assert submit_response.status_code == 200

    approve_response = client.post(
        f"/api/v1/workflow/scenes/{scene_id}/approve",
        headers=director_headers,
        json={"stage_key": "storyboard"},
    )
    assert approve_response.status_code == 200

    scene_response = client.get(f"/api/v1/scenes/{scene_id}", headers=director_headers)
    assert scene_response.status_code == 200
    stage_progress = scene_response.json()["stageProgress"]
    assert stage_progress["layout_character"]["status"] == "pending"
    assert stage_progress["layout_background"]["status"] == "pending"


def test_approved_stage_asset_cannot_be_deleted(client: TestClient) -> None:
    director_headers = {"X-User-ID": "2"}
    artist_headers = {"X-User-ID": "5"}

    create_scene_response = client.post(
        "/api/v1/scenes",
        headers=director_headers,
        json={
            "project_id": 1,
            "scene_group_id": 1,
            "name": "SC_APPROVED_ASSET_LOCK",
            "level": "B",
            "stage_template": "ai_single_frame",
            "pipeline": "ai_single_frame",
        },
    )
    assert create_scene_response.status_code == 201
    scene_id = create_scene_response.json()["id"]

    create_stage_asset(
        client,
        artist_headers,
        project_id=1,
        scene_group_id=1,
        scene_id=scene_id,
        stage_key="storyboard",
        original_name="approved_stage_guard_storyboard.png",
    )

    submit_response = client.post(
        f"/api/v1/workflow/scenes/{scene_id}/submit",
        headers=artist_headers,
        json={"stage_key": "storyboard"},
    )
    assert submit_response.status_code == 200

    approve_response = client.post(
        f"/api/v1/workflow/scenes/{scene_id}/approve",
        headers=director_headers,
        json={"stage_key": "storyboard"},
    )
    assert approve_response.status_code == 200

    create_asset_response = client.post(
        "/api/v1/assets",
        headers=artist_headers,
        json={
            "project_id": 1,
            "scene_group_id": 1,
            "scene_id": scene_id,
            "stage_key": "storyboard",
            "asset_type": "original",
            "media_type": "image",
            "original_name": "approved_storyboard.png",
        },
    )
    assert create_asset_response.status_code == 201
    asset_id = create_asset_response.json()["id"]

    delete_response = client.delete(f"/api/v1/assets/{asset_id}", headers=artist_headers)
    assert delete_response.status_code == 409
    assert delete_response.json()["detail"] == "Approved stage assets cannot be deleted"


def test_scene_with_review_history_cannot_be_deleted(client: TestClient) -> None:
    director_headers = {"X-User-ID": "2"}
    artist_headers = {"X-User-ID": "5"}

    create_scene_response = client.post(
        "/api/v1/scenes",
        headers=director_headers,
        json={
            "project_id": 1,
            "scene_group_id": 1,
            "name": "SC_DELETE_GUARD",
            "level": "B",
            "stage_template": "ai_single_frame",
            "pipeline": "ai_single_frame",
        },
    )
    assert create_scene_response.status_code == 201
    scene_id = create_scene_response.json()["id"]

    create_stage_asset(
        client,
        artist_headers,
        project_id=1,
        scene_group_id=1,
        scene_id=scene_id,
        stage_key="storyboard",
        original_name="delete_guard_storyboard.png",
    )

    submit_response = client.post(
        f"/api/v1/workflow/scenes/{scene_id}/submit",
        headers=artist_headers,
        json={"stage_key": "storyboard"},
    )
    assert submit_response.status_code == 200

    approve_response = client.post(
        f"/api/v1/workflow/scenes/{scene_id}/approve",
        headers=director_headers,
        json={"stage_key": "storyboard"},
    )
    assert approve_response.status_code == 200

    delete_response = client.delete(f"/api/v1/scenes/{scene_id}", headers=director_headers)
    assert delete_response.status_code == 409
    assert delete_response.json()["detail"] == "Scene with review history cannot be deleted"


def test_annotation_update_and_attachment_roundtrip(client: TestClient) -> None:
    headers = {"X-User-ID": "2"}
    image_buffer = BytesIO()
    Image.new("RGB", (320, 180), (240, 240, 255)).save(image_buffer, format="PNG")
    image_bytes = image_buffer.getvalue()

    asset_response = client.post(
        "/api/v1/assets",
        headers=headers,
        json={
            "project_id": 1,
            "scene_group_id": 1,
            "scene_id": 1,
            "stage_key": "correction",
            "asset_type": "markup",
            "media_type": "image",
            "original_name": "annotation-base.png",
        },
    )
    assert asset_response.status_code == 201
    asset = asset_response.json()

    upload_response = client.post(
        f"/api/v1/upload/assets/{asset['id']}/file",
        headers=headers,
        files={"file": ("annotation-base.png", image_bytes, "image/png")},
    )
    assert upload_response.status_code == 200

    create_response = client.post(
        "/api/v1/annotations",
        headers=headers,
        json={
            "project_id": 1,
            "target_asset_id": asset["id"],
            "frame_number": 120,
            "timestamp_seconds": 1.0,
            "canvas_json": {"objects": [{"type": "arrow", "x1": 20, "y1": 20, "x2": 220, "y2": 120, "stroke": "#ff0000", "strokeWidth": 6}]},
            "summary": "需要调整节奏",
        },
    )
    assert create_response.status_code == 201
    annotation = create_response.json()
    assert annotation["targetVersion"] == 1
    assert annotation["overlayUrl"].endswith(".png")
    assert annotation["mergedUrl"].endswith(".png")
    from app.core.config import settings
    assert (settings.media_root_path / annotation["overlayPath"]).exists()
    assert (settings.media_root_path / annotation["mergedPath"]).exists()

    update_response = client.put(
        f"/api/v1/annotations/{annotation['id']}",
        headers=headers,
        json={
            "frame_number": 121,
            "summary": "第121帧更准确",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["frameNumber"] == 121
    assert updated["overlayUrl"].endswith(".png")

    attachment_response = client.post(
        f"/api/v1/annotations/{annotation['id']}/attachments",
        headers=headers,
        json={
            "filename": "director-comment.png",
            "media_type": "image",
            "public_url": "/media/anno/director-comment.png",
            "size_bytes": 99,
        },
    )
    assert attachment_response.status_code == 200

    get_response = client.get(f"/api/v1/annotations/{annotation['id']}", headers=headers)
    assert get_response.status_code == 200
    fetched = get_response.json()
    assert len(fetched["attachments"]) == 1


def test_video_upload_generates_thumbnail_and_metadata(client: TestClient) -> None:
    headers = {"X-User-ID": "5"}
    tmp_video = ROOT_DIR / "tests" / "tmp_test_video.mp4"
    writer = cv2.VideoWriter(str(tmp_video), cv2.VideoWriter_fourcc(*"mp4v"), 12.0, (160, 90))
    for idx in range(12):
        frame = np.zeros((90, 160, 3), dtype=np.uint8)
        frame[:, :] = (idx * 10, 80, 180)
        writer.write(frame)
    writer.release()
    video_bytes = tmp_video.read_bytes()

    create_response = client.post(
        "/api/v1/assets",
        headers=headers,
        json={
            "project_id": 1,
            "scene_group_id": 2,
            "scene_id": 5,
            "stage_key": "final",
            "asset_type": "preview",
            "media_type": "video",
            "original_name": "shot005_preview.mp4",
            "metadata_json": {"durationSeconds": 3.2, "width": 1280, "height": 720},
        },
    )
    assert create_response.status_code == 201
    asset = create_response.json()
    assert asset["thumbnailUrl"] is None

    upload_response = client.post(
        f"/api/v1/upload/assets/{asset['id']}/file",
        headers=headers,
        files={"file": ("shot005_preview.mp4", video_bytes, "video/mp4")},
    )
    assert upload_response.status_code == 200
    payload = upload_response.json()
    assert payload["thumbnail_url"].endswith(".png")
    assert payload["metadata_json"]["sizeBytes"] == len(video_bytes)
    assert payload["metadata_json"]["contentType"] == "video/mp4"
    assert payload["metadata_json"]["width"] == 160
    assert payload["metadata_json"]["height"] == 90
    assert payload["metadata_json"]["frameCount"] >= 12
    assert payload["metadata_json"]["fps"] is not None
    assert payload["metadata_json"]["durationSeconds"] is not None

    asset_response = client.get(f"/api/v1/assets/{asset['id']}", headers=headers)
    assert asset_response.status_code == 200
    stored = asset_response.json()
    assert stored["mediaType"] == "video"
    assert stored["thumbnailUrl"].endswith(".png")
    from app.core.config import settings
    assert (settings.media_root_path / stored["thumbnailPath"]).exists()
    tmp_video.unlink(missing_ok=True)


def test_bank_reference_ref_count_and_detach(client: TestClient) -> None:
    headers = {"X-User-ID": "4"}
    material_create = client.post(
        "/api/v1/bank/materials",
        headers=headers,
        json={
            "project_id": 1,
            "source_asset_id": 2,
            "name": "测试兼用素材",
            "character_name": "主角",
            "part_name": "身体",
            "pose": "站立",
            "angle": "侧面",
        },
    )
    assert material_create.status_code == 201
    material = material_create.json()

    create_response = client.post(
        "/api/v1/bank/references",
        headers=headers,
        json={
            "bank_material_id": material["id"],
            "project_id": 1,
            "scene_id": 2,
            "stage_key": "ai_draw",
        },
    )
    assert create_response.status_code == 201
    reference = create_response.json()
    assert reference["version"] == 1

    material_response = client.get(f"/api/v1/bank/materials/{material['id']}", headers=headers)
    assert material_response.status_code == 200
    assert material_response.json()["refCount"] == 1

    duplicate_response = client.post(
        "/api/v1/bank/references",
        headers=headers,
        json={
            "bank_material_id": material["id"],
            "project_id": 1,
            "scene_id": 2,
            "stage_key": "ai_draw",
        },
    )
    assert duplicate_response.status_code == 400

    detach_response = client.post(
        f"/api/v1/bank/references/{reference['id']}/detach",
        headers=headers,
        json={},
    )
    assert detach_response.status_code == 200
    detached = detach_response.json()
    assert detached["status"] == "detached"
    assert detached["detachedAssetId"] is not None

    material_response = client.get(f"/api/v1/bank/materials/{material['id']}", headers=headers)
    assert material_response.status_code == 200
    assert material_response.json()["refCount"] == 0

    delete_response = client.delete(f"/api/v1/bank/materials/{material['id']}", headers=headers)
    assert delete_response.status_code == 400


def test_bank_material_can_be_updated(client: TestClient) -> None:
    headers = {"X-User-ID": "4"}
    material_create = client.post(
        "/api/v1/bank/materials",
        headers=headers,
        json={
            "project_id": 1,
            "source_asset_id": 2,
            "name": "更新前素材",
            "character_name": "主角",
            "part_name": "头部",
            "pose": "站立",
            "angle": "正面",
        },
    )
    assert material_create.status_code == 201
    material = material_create.json()

    update_response = client.put(
        f"/api/v1/bank/materials/{material['id']}",
        headers=headers,
        json={
            "name": "更新后素材",
            "character_name": "路飞",
            "part_name": "身体",
            "pose": "坐姿",
            "angle": "侧面",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["name"] == "更新后素材"
    assert updated["character"] == "路飞"
    assert updated["part"] == "身体"
    assert updated["pose"] == "坐姿"
    assert updated["angle"] == "侧面"




def test_reference_validation_and_summary(client: TestClient) -> None:
    headers = {"X-User-ID": "2"}
    create_response = client.post(
        "/api/v1/references",
        headers=headers,
        json={
            "project_id": 1,
            "source_type": "asset",
            "source_id": 1,
            "target_type": "scene",
            "target_id": 1,
            "relation_type": "mention",
        },
    )
    assert create_response.status_code == 201

    duplicate = client.post(
        "/api/v1/references",
        headers=headers,
        json={
            "project_id": 1,
            "source_type": "asset",
            "source_id": 1,
            "target_type": "scene",
            "target_id": 1,
            "relation_type": "mention",
        },
    )
    assert duplicate.status_code == 409

    summary = client.get(
        "/api/v1/references/summary/by-object",
        headers=headers,
        params={"project_id": 1, "object_type": "asset", "object_id": 1},
    )
    assert summary.status_code == 200
    assert summary.json()["outgoingCount"] >= 1


def test_async_job_export_and_worker_runner(client: TestClient) -> None:
    headers = {"X-User-ID": "4"}
    create_response = client.post(
        "/api/v1/async-jobs/projects/1/export",
        headers=headers,
        json={"priority": 40},
    )
    assert create_response.status_code == 201
    job = create_response.json()
    assert job["status"] == "pending"
    assert job["jobType"] == "project_export"

    from app.core.database import SessionLocal
    from app.workers.runner import WorkerRunner

    db = SessionLocal()
    try:
        worked = asyncio.run(WorkerRunner(db).run_once())
        assert worked is True
    finally:
        db.close()

    fetch_response = client.get(f"/api/v1/async-jobs/{job['id']}", headers=headers)
    assert fetch_response.status_code == 200
    completed = fetch_response.json()
    assert completed["status"] == "success"
    export_url = completed["resultJson"]["exportUrl"]
    from app.core.config import settings
    export_path = settings.media_root_path / export_url.removeprefix("/media/")
    assert export_path.exists()
    with zipfile.ZipFile(export_path) as zf:
        names = zf.namelist()
        assert "manifest.json" in names


def test_async_job_retry_endpoint(client: TestClient) -> None:
    headers = {"X-User-ID": "4"}
    create_response = client.post(
        "/api/v1/async-jobs",
        headers=headers,
        json={
            "project_id": 1,
            "job_type": "annotation_render",
            "payload_json": {"annotation_id": 999999},
            "priority": 80,
            "max_retries": 2,
        },
    )
    assert create_response.status_code == 201
    job = create_response.json()

    from app.core.database import SessionLocal
    from app.workers.runner import WorkerRunner

    db = SessionLocal()
    try:
        asyncio.run(WorkerRunner(db).run_once())
    finally:
        db.close()

    failed_fetch = client.get(f"/api/v1/async-jobs/{job['id']}", headers=headers)
    assert failed_fetch.status_code == 200
    failed_job = failed_fetch.json()
    assert failed_job["status"] in {"pending", "failed"}
    assert failed_job["retryCount"] == 1

    retry_response = client.post(
        f"/api/v1/async-jobs/{job['id']}/retry",
        headers=headers,
        json={"reset_error": True},
    )
    assert retry_response.status_code == 200
    retried = retry_response.json()
    assert retried["status"] == "pending"
    assert retried["retryCount"] == 2


def test_submit_review_notifies_only_admin_director_and_producer(client: TestClient) -> None:
    create_stage_asset(
        client,
        {"X-User-ID": "5"},
        project_id=1,
        scene_group_id=1,
        scene_id=1,
        stage_key="correction",
        original_name="notify_correction.png",
    )

    submit_response = client.post(
        "/api/v1/workflow/scenes/1/submit",
        headers={"X-User-ID": "5"},
        json={"stage_key": "correction"},
    )
    assert submit_response.status_code == 200

    director_notifications = client.get("/api/v1/notifications", headers={"X-User-ID": "2"})
    producer_notifications = client.get("/api/v1/notifications", headers={"X-User-ID": "4"})
    artist_notifications = client.get("/api/v1/notifications", headers={"X-User-ID": "5"})
    visitor_notifications = client.get("/api/v1/notifications", headers={"X-User-ID": "8"})

    assert any(item["type"] == "review_required" and item["payloadJson"]["scene_id"] == 1 for item in director_notifications.json())
    assert any(item["type"] == "review_required" and item["payloadJson"]["scene_id"] == 1 for item in producer_notifications.json())
    assert not any(item["type"] == "review_required" and item["payloadJson"]["scene_id"] == 1 for item in artist_notifications.json())
    assert not any(item["type"] == "review_required" and item["payloadJson"]["scene_id"] == 1 for item in visitor_notifications.json())


def test_workflow_submit_approve_reject_and_resubmit_flow(client: TestClient) -> None:
    create_scene = client.post(
        "/api/v1/scenes",
        headers={"X-User-ID": "2"},
        json={
            "project_id": 1,
            "scene_group_id": 1,
            "name": f"FLOW_{uuid.uuid4().hex[:6]}",
            "description": "workflow regression",
            "level": "B",
            "stage_template": "ai_single_frame",
            "pipeline": "ai_single_frame",
            "frame_count": 1,
            "sort_order": 999,
        },
    )
    assert create_scene.status_code == 201
    scene_id = create_scene.json()["id"]

    create_stage_asset(
        client,
        {"X-User-ID": "5"},
        project_id=1,
        scene_group_id=1,
        scene_id=scene_id,
        stage_key="storyboard",
        original_name="workflow_storyboard.png",
    )

    submit_response = client.post(
        f"/api/v1/workflow/scenes/{scene_id}/submit",
        headers={"X-User-ID": "5"},
        json={"stage_key": "storyboard"},
    )
    assert submit_response.status_code == 200
    submit_record = submit_response.json()[0]
    assert submit_record["action"] == "submit"
    assert submit_record["toStatus"] == "reviewing"

    approve_response = client.post(
        f"/api/v1/workflow/scenes/{scene_id}/approve",
        headers={"X-User-ID": "2"},
        json={"stage_key": "storyboard", "comment": "approved"},
    )
    assert approve_response.status_code == 200
    approve_records = approve_response.json()
    assert any(item["action"] == "approve" and item["toStatus"] == "approved" for item in approve_records)

    scene_after_approve = client.get(f"/api/v1/scenes/{scene_id}", headers={"X-User-ID": "2"})
    assert scene_after_approve.status_code == 200
    assert scene_after_approve.json()["stageProgress"]["ai_draw"]["status"] == "pending"

    accept_final = client.post(
        f"/api/v1/scenes/{scene_id}/stages/ai_draw/accept",
        headers={"X-User-ID": "5"},
    )
    assert accept_final.status_code == 200

    submit_final = client.post(
        f"/api/v1/workflow/scenes/{scene_id}/submit",
        headers={"X-User-ID": "5"},
        json={"stage_key": "ai_draw"},
    )
    assert submit_final.status_code == 200

    reject_response = client.post(
        f"/api/v1/workflow/scenes/{scene_id}/reject",
        headers={"X-User-ID": "2"},
        json={"stage_key": "ai_draw", "comment": "fix ai draw"},
    )
    assert reject_response.status_code == 200
    reject_records = reject_response.json()
    assert any(item["action"] == "reject" and item["toStatus"] == "rejected" for item in reject_records)
    assert any(item["action"] == "rollback" and item["stageKey"] == "storyboard" for item in reject_records)

    resubmit_response = client.post(
        f"/api/v1/workflow/scenes/{scene_id}/resubmit",
        headers={"X-User-ID": "5"},
        json={"stage_key": "ai_draw"},
    )
    assert resubmit_response.status_code == 200
    assert resubmit_response.json()["action"] == "resubmit"


def test_submit_stage_requires_existing_assets(client: TestClient) -> None:
    headers = {"X-User-ID": "2"}
    create_scene = client.post(
        "/api/v1/scenes",
        headers=headers,
        json={
            "project_id": 1,
            "scene_group_id": 1,
            "name": f"NO_ASSET_{uuid.uuid4().hex[:6]}",
            "description": "missing asset validation",
            "level": "B",
            "stage_template": "ai_single_frame",
            "pipeline": "ai_single_frame",
            "frame_count": 1,
            "sort_order": 998,
        },
    )
    assert create_scene.status_code == 201
    scene_id = create_scene.json()["id"]

    submit_response = client.post(
        f"/api/v1/workflow/scenes/{scene_id}/submit",
        headers={"X-User-ID": "5"},
        json={"stage_key": "storyboard"},
    )
    assert submit_response.status_code == 409
    assert submit_response.json()["detail"] == "Stage 'storyboard' has no assets and cannot be submitted"


def test_auth_login_cookie_and_bearer_token_flow(client: TestClient) -> None:
    login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "admin123"})
    assert login.status_code == 200
    payload = login.json()
    assert payload["user"]["username"] == "admin"
    token = payload["token"]

    bearer_me = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert bearer_me.status_code == 200
    assert bearer_me.json()["role"] == "admin"

    logout = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
    assert logout.status_code == 200
    invalid_after_logout = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert invalid_after_logout.status_code == 401


def test_admin_account_prompt_dashboard_and_audit_endpoints(client: TestClient) -> None:
    headers = {"X-User-ID": "1"}
    create_account = client.post(
        "/api/v1/accounts",
        headers=headers,
        json={
            "name": "联调账号",
            "email": "integration-account@example.com",
            "status": "active",
            "project_ids": [1],
            "remark": "smoke",
        },
    )
    assert create_account.status_code == 201
    account = create_account.json()
    assert account["projectIds"] == [1]

    verify_account = client.post(
        f"/api/v1/accounts/{account['id']}/verify",
        headers=headers,
        json={"status": "cooldown", "remark": "manual verify"},
    )
    assert verify_account.status_code == 200
    assert verify_account.json()["status"] == "cooldown"

    prompt = client.post(
        "/api/v1/prompts",
        headers=headers,
        json={
            "name": "联调 Prompt",
            "content": "测试提示词",
            "scope": "project",
            "project_id": 1,
            "resolution": "2k",
        },
    )
    assert prompt.status_code == 201
    prompt_id = prompt.json()["id"]

    dashboard = client.get("/api/v1/admin/dashboard", headers=headers)
    assert dashboard.status_code == 200
    assert dashboard.json()["accountCount"] >= 1

    audits = client.get("/api/v1/admin/audit-logs", headers=headers)
    assert audits.status_code == 200
    assert any(item["action"] == "prompt.create" and item["targetType"] == "prompt" for item in audits.json())

    delete_prompt = client.delete(f"/api/v1/prompts/{prompt_id}", headers=headers)
    assert delete_prompt.status_code == 204


def test_generation_templates_image_groups_tasks_and_results_flow(client: TestClient) -> None:
    headers = {"X-User-ID": "5"}
    group = client.post(
        "/api/v1/image-groups",
        headers=headers,
        json={
            "name": "联调图组",
            "description": "smoke",
            "project_id": 1,
            "images": [
                {
                    "name": "ref.png",
                    "url": "https://example.com/ref.png",
                    "sort_order": 0,
                }
            ],
        },
    )
    assert group.status_code == 201
    image_group = group.json()
    assert len(image_group["images"]) == 1

    template = client.post(
        "/api/v1/templates",
        headers=headers,
        json={
            "name": "联调模板",
            "description": "smoke",
            "snapshot": {
                "imageGroupId": image_group["id"],
                "prompt": "测试模板",
                "aspectRatio": "auto",
                "resolution": "2k",
                "count": 4,
            },
        },
    )
    assert template.status_code == 201

    task = client.post(
        "/api/v1/generation/tasks",
        headers=headers,
        json={
            "project_id": 1,
            "scene_id": 1,
            "stage": "keyframe",
            "image_group_id": image_group["id"],
            "prompt_content": "测试生成任务",
            "status": "pending",
        },
    )
    assert task.status_code == 201
    task_id = task.json()["id"]

    result = client.post(
        "/api/v1/generation/results",
        headers=headers,
        json={
            "task_id": task_id,
            "project_id": 1,
            "scene_id": 1,
            "stage": "keyframe",
            "image_group_id": image_group["id"],
            "name": "联调结果图",
            "url": "https://example.com/result.png",
            "status": "pending",
        },
    )
    assert result.status_code == 201
    result_id = result.json()["id"]

    submit = client.post(
        f"/api/v1/generation/results/{result_id}/submit",
        headers=headers,
        json={"name": "联调结果图_待审"},
    )
    assert submit.status_code == 200
    assert submit.json()["status"] == "submitted"

    review = client.post(
        f"/api/v1/generation/results/{result_id}/review",
        headers={"X-User-ID": "2"},
        json={"status": "approved", "comment": "通过"},
    )
    assert review.status_code == 200
    assert review.json()["status"] == "approved"

    approved = client.get("/api/v1/generation/results/approved", headers=headers, params={"scene_id": 1})
    assert approved.status_code == 200
    assert any(item["id"] == result_id for item in approved.json())


def test_admin_user_project_membership_and_password_management(client: TestClient) -> None:
    admin_headers = {"X-User-ID": "1"}
    create_user = client.post(
        "/api/v1/users",
        headers=admin_headers,
        json={
            "username": "newadminflow",
            "display_name": "新用户",
            "email": "newadminflow@example.com",
            "role": "artist",
            "password": "initpass123",
            "is_active": True,
            "project_ids": [1],
        },
    )
    assert create_user.status_code == 201
    user = create_user.json()
    assert user["projectIds"] == [1]

    rotate = client.post(f"/api/v1/users/{user['id']}/rotate-api-key", headers=admin_headers)
    assert rotate.status_code == 200
    assert rotate.json()["apiKey"]

    reset_password = client.post(
        f"/api/v1/users/{user['id']}/reset-password",
        headers=admin_headers,
        json={"new_password": "newpass123"},
    )
    assert reset_password.status_code == 200

    login = client.post("/api/v1/auth/login", json={"username": "newadminflow", "password": "newpass123"})
    assert login.status_code == 200

    update_project_members = client.post(
        "/api/v1/projects/1/members",
        headers={"X-User-ID": "2"},
        json={"user_id": user["id"], "role_in_project": "artist"},
    )
    assert update_project_members.status_code in {200, 409}

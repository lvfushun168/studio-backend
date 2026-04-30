from __future__ import annotations

import importlib
import os
import subprocess
import sys
import uuid
from pathlib import Path

import psycopg
import pytest
from fastapi.testclient import TestClient


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


def test_assets_are_scoped_to_project_membership(client: TestClient) -> None:
    response = client.get("/api/v1/assets", headers={"X-User-ID": "5"})
    assert response.status_code == 200
    payload = response.json()
    assert payload
    assert all(item["projectId"] == 1 for item in payload)


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


def test_annotation_update_and_attachment_roundtrip(client: TestClient) -> None:
    headers = {"X-User-ID": "2"}
    create_response = client.post(
        "/api/v1/annotations",
        headers=headers,
        json={
            "project_id": 1,
            "target_asset_id": 10,
            "frame_number": 120,
            "timestamp_seconds": 1.0,
            "canvas_json": {"objects": [{"type": "arrow"}]},
            "summary": "需要调整节奏",
        },
    )
    assert create_response.status_code == 201
    annotation = create_response.json()
    assert annotation["targetVersion"] == 1

    update_response = client.put(
        f"/api/v1/annotations/{annotation['id']}",
        headers=headers,
        json={
            "frame_number": 121,
            "summary": "第121帧更准确",
            "overlay_url": "/media/anno/121.png",
        },
    )
    assert update_response.status_code == 200
    updated = update_response.json()
    assert updated["frameNumber"] == 121
    assert updated["overlayUrl"] == "/media/anno/121.png"

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


def test_bank_reference_ref_count_and_detach(client: TestClient) -> None:
    headers = {"X-User-ID": "4"}
    create_response = client.post(
        "/api/v1/bank/references",
        headers=headers,
        json={
            "bank_material_id": 1,
            "project_id": 1,
            "scene_id": 2,
            "stage_key": "ai_draw",
        },
    )
    assert create_response.status_code == 201
    reference = create_response.json()
    assert reference["version"] == 1

    material_response = client.get("/api/v1/bank/materials/1", headers=headers)
    assert material_response.status_code == 200
    assert material_response.json()["refCount"] == 2

    detach_response = client.post(
        f"/api/v1/bank/references/{reference['id']}/detach",
        headers=headers,
        json={"detached_asset_id": 2},
    )
    assert detach_response.status_code == 200
    detached = detach_response.json()
    assert detached["status"] == "detached"
    assert detached["detachedAssetId"] == 2

    material_response = client.get("/api/v1/bank/materials/1", headers=headers)
    assert material_response.status_code == 200
    assert material_response.json()["refCount"] == 1


def test_submit_review_notifies_only_admin_director_and_producer(client: TestClient) -> None:
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

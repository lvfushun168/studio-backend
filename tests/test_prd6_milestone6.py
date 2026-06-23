from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import engine, get_db
from app.main import app
from app.models.project import Project, SceneGroup, UserProjectMembership
from app.models.user import User


@pytest.fixture
def m6_client():
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    suffix = uuid.uuid4().hex[:8]
    producer = User(username=f"m6_producer_{suffix}", display_name="制片", role="producer", is_active=True)
    director = User(username=f"m6_director_{suffix}", display_name="导演", role="director", is_active=True)
    artist = User(username=f"m6_artist_{suffix}", display_name="画师", role="artist", is_active=True)
    db.add_all([producer, director, artist])
    db.flush()
    project = Project(name=f"M6 E2E {suffix}", created_by=producer.id)
    db.add(project)
    db.flush()
    for user in (producer, director, artist):
        db.add(UserProjectMembership(user_id=user.id, project_id=project.id, role_in_project=user.role))
    group = SceneGroup(project_id=project.id, name="M6 镜头组")
    db.add(group)
    db.commit()
    current = {"user": producer}

    def override_db():
        yield db

    def override_user():
        return current["user"]

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    with TestClient(app) as client:
        yield client, current, producer, director, artist, project, group
    app.dependency_overrides.clear()
    db.close()
    transaction.rollback()
    connection.close()


def ok(response):
    assert response.status_code in {200, 201, 204}, response.text
    return None if response.status_code == 204 else response.json()


def create_asset(client, project, group, scene, step, name):
    return ok(client.post("/api/v1/assets", json={
        "projectId": project.id,
        "sceneGroupId": group.id,
        "sceneId": scene["id"],
        "stageKey": step["stageKey"],
        "sceneWorkStepId": step["id"],
        "assetUsage": "step_draft",
        "assetType": "original",
        "mediaType": "image",
        "originalName": name,
    }))


def test_m6_forward_reverse_batch_and_permissions(m6_client):
    client, current, producer, director, artist, project, group = m6_client

    template = ok(client.post("/api/v1/work-step-templates", json={
        "scope": "project",
        "projectId": project.id,
        "name": "Layout 人物完整流程",
        "stageKey": "layout_character",
        "isDefault": True,
        "items": [
            {"stepKey": "rough", "name": "草图", "sortOrder": 10},
            {"stepKey": "cleanup", "name": "清线", "sortOrder": 20},
        ],
    }))
    assert template["isDefault"] is True

    current["user"] = artist
    assert client.post("/api/v1/work-step-templates", json={
        "scope": "project", "projectId": project.id, "name": "越权", "stageKey": "keyframe",
        "items": [{"stepKey": "forbidden", "name": "越权步骤", "sortOrder": 10}],
    }).status_code == 403

    current["user"] = producer
    scene = ok(client.post("/api/v1/scenes", json={
        "projectId": project.id,
        "sceneGroupId": group.id,
        "name": "SC-M6-001",
        "stageTemplate": "standard",
        "pipeline": "standard",
    }))
    entry_steps = ok(client.get(f"/api/v1/scenes/{scene['id']}/stages/storyboard/work-steps"))
    assert entry_steps and entry_steps[0]["name"] == "阶段交付"
    ok(client.post("/api/v1/assets", json={
        "projectId": project.id, "sceneGroupId": group.id, "sceneId": scene["id"],
        "stageKey": "storyboard", "assetUsage": "stage_asset", "assetType": "original",
        "mediaType": "image", "originalName": "storyboard.png",
    }))
    ok(client.post(f"/api/v1/workflow/scenes/{scene['id']}/initialize-entry"))

    steps = ok(client.get(f"/api/v1/scenes/{scene['id']}/stages/layout_character/work-steps"))
    assert [step["name"] for step in steps] == ["草图", "清线"]
    for step in steps:
        ok(client.patch(f"/api/v1/work-steps/{step['id']}", json={"assigneeId": artist.id}))

    current["user"] = artist
    rough = ok(client.post(f"/api/v1/work-steps/{steps[0]['id']}/start"))
    rough_asset = create_asset(client, project, group, scene, rough, "rough-v1.png")
    assert ok(client.post(f"/api/v1/work-steps/{rough['id']}/submit", json={"assetIds": [rough_asset["id"]]}))["version"] == 1
    assert ok(client.post(f"/api/v1/work-steps/{rough['id']}/withdraw"))["status"] == "withdrawn"
    assert ok(client.post(f"/api/v1/work-steps/{rough['id']}/submit", json={"assetIds": [rough_asset["id"]]}))["version"] == 2

    cleanup = ok(client.post(f"/api/v1/work-steps/{steps[1]['id']}/start"))
    cleanup_asset = create_asset(client, project, group, scene, cleanup, "cleanup-v1.png")
    ok(client.post(f"/api/v1/work-steps/{cleanup['id']}/submit", json={"assetIds": [cleanup_asset["id"]]}))
    ok(client.post(f"/api/v1/workflow/scenes/{scene['id']}/submit", json={"stageKey": "layout_character"}))

    current["user"] = director
    ok(client.post(f"/api/v1/workflow/scenes/{scene['id']}/reject", json={
        "stageKey": "layout_character", "comment": "草图比例需修正", "workStepIds": [rough["id"]],
    }))
    assert ok(client.get(f"/api/v1/work-steps/{rough['id']}"))["status"] == "needs_fix"

    current["user"] = artist
    ok(client.post(f"/api/v1/work-steps/{rough['id']}/start"))
    rough_asset_v3 = create_asset(client, project, group, scene, rough, "rough-v3.png")
    assert ok(client.post(f"/api/v1/work-steps/{rough['id']}/submit", json={"assetIds": [rough_asset_v3["id"]]}))["version"] == 3
    ok(client.post(f"/api/v1/workflow/scenes/{scene['id']}/submit", json={"stageKey": "layout_character"}))
    current["user"] = director
    ok(client.post(f"/api/v1/workflow/scenes/{scene['id']}/approve", json={"stageKey": "layout_character"}))
    assert [step["status"] for step in ok(client.get(
        f"/api/v1/scenes/{scene['id']}/stages/layout_character/work-steps"
    ))] == ["done", "done"]

    current["user"] = producer
    replacement = ok(client.post("/api/v1/work-step-templates", json={
        "scope": "project", "projectId": project.id, "name": "一原覆盖模板", "stageKey": "keyframe",
        "items": [
            {"stepKey": "key_draft", "name": "一原草稿", "sortOrder": 10},
            {"stepKey": "self_check", "name": "自检", "sortOrder": 20, "isRequired": False},
        ],
    }))
    targets = [{"sceneId": scene["id"], "stageKey": "keyframe"}]
    preview = ok(client.post("/api/v1/work-steps/batch-apply-template", json={
        "templateId": replacement["id"], "mode": "replace", "previewOnly": True, "targets": targets,
    }))
    assert preview["targetCount"] == 1
    ok(client.post("/api/v1/work-steps/batch-apply-template", json={
        "templateId": replacement["id"], "mode": "replace", "previewOnly": False, "targets": targets,
    }))
    key_steps = ok(client.get(f"/api/v1/scenes/{scene['id']}/stages/keyframe/work-steps"))
    assert [step["stepKey"] for step in key_steps] == ["key_draft", "self_check"]
    assert client.delete(f"/api/v1/work-steps/{key_steps[1]['id']}").status_code == 204
    assert ok(client.get(f"/api/v1/work-steps/{key_steps[1]['id']}"))["status"] == "cancelled"

    matrix = ok(client.get("/api/v1/production-matrix", params={"project_id": project.id}))
    progress = ok(client.get(f"/api/v1/progress/projects/{project.id}/work-steps"))
    assert matrix["summary"]["sceneCount"] == 1
    assert progress["summary"]["totalScenes"] == 1

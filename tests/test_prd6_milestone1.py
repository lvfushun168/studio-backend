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
def milestone_client():
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    suffix = uuid.uuid4().hex[:8]
    producer = User(username=f"m1_producer_{suffix}", display_name="M1 Producer", role="producer", is_active=True)
    artist = User(username=f"m1_artist_{suffix}", display_name="M1 Artist", role="artist", is_active=True)
    db.add_all([producer, artist])
    db.flush()
    project = Project(name=f"M1 Project {suffix}", created_by=producer.id)
    db.add(project)
    db.flush()
    db.add_all([
        UserProjectMembership(user_id=producer.id, project_id=project.id, role_in_project="producer"),
        UserProjectMembership(user_id=artist.id, project_id=project.id, role_in_project="artist"),
    ])
    group = SceneGroup(project_id=project.id, name="EP01-A", sort_order=10)
    db.add(group)
    db.commit()

    def override_db():
        yield db

    current_user = {"value": producer}

    def override_user():
        return current_user["value"]

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    with TestClient(app) as client:
        yield client, db, producer, artist, project, group, current_user

    app.dependency_overrides.clear()
    db.close()
    transaction.rollback()
    connection.close()


def test_template_crud_permissions_and_scene_materialization(milestone_client):
    client, _, producer, artist, project, group, current_user = milestone_client
    payload = {
        "scope": "project",
        "projectId": project.id,
        "name": "分镜标准步骤",
        "stageKey": "storyboard",
        "isDefault": True,
        "items": [
            {"stepKey": "rough", "name": "草图", "sortOrder": 10},
            {"stepKey": "cleanup", "name": "清线", "sortOrder": 20},
        ],
    }
    current_user["value"] = artist
    denied = client.post("/api/v1/work-step-templates", json=payload)
    assert denied.status_code == 403

    current_user["value"] = producer
    created = client.post("/api/v1/work-step-templates", json=payload)
    assert created.status_code == 201, created.text
    template = created.json()
    assert [item["stepKey"] for item in template["items"]] == ["rough", "cleanup"]

    listed = client.get(
        "/api/v1/work-step-templates",
        params={"project_id": project.id, "include_inactive": True},
        headers={"X-Test-User-ID": str(producer.id)},
    )
    assert listed.status_code == 200
    assert [item["id"] for item in listed.json()] == [template["id"]]

    updated = client.put(
        f"/api/v1/work-step-templates/{template['id']}",
        json={"description": "用于 M1 验收", "items": payload["items"]},
        headers={"X-Test-User-ID": str(producer.id)},
    )
    assert updated.status_code == 200, updated.text
    assert updated.json()["description"] == "用于 M1 验收"

    scene_payload = {
        "project_id": project.id,
        "scene_group_id": group.id,
        "name": "SC-M1-001",
        "stage_template": "standard",
        "pipeline": "standard",
    }
    scene_response = client.post("/api/v1/scenes", json=scene_payload, headers={"X-Test-User-ID": str(producer.id)})
    assert scene_response.status_code == 201, scene_response.text
    scene = scene_response.json()

    all_steps = client.get(
        "/api/v1/work-steps",
        params={"scene_id": scene["id"]},
        headers={"X-Test-User-ID": str(producer.id)},
    )
    assert all_steps.status_code == 200, all_steps.text
    items = all_steps.json()["items"]
    assert len({item["stageKey"] for item in items}) == len(scene["stageProgresses"])
    storyboard = [item for item in items if item["stageKey"] == "storyboard"]
    assert [item["stepKey"] for item in storyboard] == ["rough", "cleanup"]
    default_steps = [item for item in items if item["stageKey"] != "storyboard"]
    assert default_steps and all(item["name"] == "阶段交付" for item in default_steps)

    stage_steps = client.get(
        f"/api/v1/scenes/{scene['id']}/stages/storyboard/work-steps",
        headers={"X-Test-User-ID": str(producer.id)},
    )
    assert stage_steps.status_code == 200
    assert [item["id"] for item in stage_steps.json()] == [item["id"] for item in storyboard]

    compatible_payload = {
        **scene_payload,
        "name": "SC-M1-002",
        "base_scene_id": scene["id"],
        "copy_work_steps_from_scene_id": scene["id"],
    }
    compatible_response = client.post(
        "/api/v1/scenes", json=compatible_payload, headers={"X-Test-User-ID": str(producer.id)}
    )
    assert compatible_response.status_code == 201, compatible_response.text
    compatible_scene = compatible_response.json()
    compatible_steps = client.get(
        "/api/v1/work-steps",
        params={"scene_id": compatible_scene["id"]},
        headers={"X-Test-User-ID": str(producer.id)},
    ).json()["items"]
    assert {item["id"] for item in items}.isdisjoint({item["id"] for item in compatible_steps})
    assert [(item["stageKey"], item["stepKey"]) for item in compatible_steps] == [
        (item["stageKey"], item["stepKey"]) for item in items
    ]

    manual = client.post(
        f"/api/v1/scenes/{scene['id']}/stages/storyboard/work-steps",
        json={"stepKey": "producer_check", "name": "制片检查", "sortOrder": 30, "isRequired": False},
        headers={"X-Test-User-ID": str(producer.id)},
    )
    assert manual.status_code == 201, manual.text
    patched = client.patch(
        f"/api/v1/work-steps/{manual.json()['id']}",
        json={"name": "制片复核", "priority": "high"},
        headers={"X-Test-User-ID": str(producer.id)},
    )
    assert patched.status_code == 200, patched.text
    assert patched.json()["name"] == "制片复核"
    assert patched.json()["priority"] == "high"
    cancelled = client.delete(
        f"/api/v1/work-steps/{manual.json()['id']}", headers={"X-Test-User-ID": str(producer.id)}
    )
    assert cancelled.status_code == 204
    visible_steps = client.get(
        f"/api/v1/scenes/{scene['id']}/stages/storyboard/work-steps",
        headers={"X-Test-User-ID": str(producer.id)},
    ).json()
    assert manual.json()["id"] not in {item["id"] for item in visible_steps}

    deactivated = client.delete(
        f"/api/v1/work-step-templates/{template['id']}", headers={"X-Test-User-ID": str(producer.id)}
    )
    assert deactivated.status_code == 204
    inactive_list = client.get(
        "/api/v1/work-step-templates",
        params={"project_id": project.id, "include_inactive": True},
        headers={"X-Test-User-ID": str(producer.id)},
    ).json()
    assert inactive_list[0]["isActive"] is False

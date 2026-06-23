from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import engine, get_db
from app.main import app
from app.models.project import Project, SceneGroup, UserProjectMembership
from app.models.user import User


@pytest.fixture
def milestone5_client():
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    suffix = uuid.uuid4().hex[:8]
    producer = User(username=f"m5_producer_{suffix}", display_name="制片", role="producer", is_active=True)
    director = User(username=f"m5_director_{suffix}", display_name="导演", role="director", is_active=True)
    artist = User(username=f"m5_artist_{suffix}", display_name="画师", role="artist", is_active=True)
    db.add_all([producer, director, artist]); db.flush()
    project = Project(name=f"M5 Project {suffix}", created_by=producer.id)
    db.add(project); db.flush()
    for user in (producer, director, artist):
        db.add(UserProjectMembership(user_id=user.id, project_id=project.id, role_in_project=user.role))
    group = SceneGroup(project_id=project.id, name="M5 Group")
    db.add(group); db.commit()
    current = {"user": producer}

    def override_db(): yield db
    def override_user(): return current["user"]
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    with TestClient(app) as client:
        yield client, current, producer, director, artist, project, group
    app.dependency_overrides.clear(); db.close(); transaction.rollback(); connection.close()


def _post(client, path, payload=None):
    response = client.post(path, json=payload or {})
    assert response.status_code in {200, 201, 204}, response.text
    return response


def test_project_progress_blockers_and_step_notifications(milestone5_client):
    client, current, producer, director, artist, project, group = milestone5_client
    scene = _post(client, "/api/v1/scenes", {
        "projectId": project.id, "sceneGroupId": group.id, "name": "SC-M5-001",
        "stageTemplate": "standard", "pipeline": "standard",
    }).json()
    _post(client, "/api/v1/assets", {
        "projectId": project.id, "sceneGroupId": group.id, "sceneId": scene["id"],
        "stageKey": "storyboard", "assetUsage": "stage_asset", "assetType": "original",
        "mediaType": "image", "originalName": "storyboard.png",
    })
    _post(client, f"/api/v1/workflow/scenes/{scene['id']}/initialize-entry")
    step = client.get(f"/api/v1/scenes/{scene['id']}/stages/layout_character/work-steps").json()[0]
    due_at = datetime.now(timezone.utc) - timedelta(hours=2)
    assigned = client.patch(f"/api/v1/work-steps/{step['id']}", json={
        "assigneeId": artist.id, "dueAt": due_at.isoformat(), "priority": "urgent",
    })
    assert assigned.status_code == 200, assigned.text

    current["user"] = artist
    artist_notifications = client.get("/api/v1/notifications").json()
    assert {item["type"] for item in artist_notifications} >= {"work_step_assigned", "work_step_due_changed"}
    _post(client, f"/api/v1/work-steps/{step['id']}/start")
    asset = _post(client, "/api/v1/assets", {
        "projectId": project.id, "sceneGroupId": group.id, "sceneId": scene["id"],
        "stageKey": "layout_character", "sceneWorkStepId": step["id"], "assetUsage": "step_draft",
        "assetType": "original", "mediaType": "image", "originalName": "layout.png",
    }).json()
    _post(client, f"/api/v1/work-steps/{step['id']}/submit", {"assetIds": [asset["id"]]})
    _post(client, f"/api/v1/workflow/scenes/{scene['id']}/submit", {"stageKey": "layout_character"})

    current["user"] = producer
    assert "work_step_submitted" in {item["type"] for item in client.get("/api/v1/notifications").json()}
    current["user"] = director
    assert "work_step_submitted" in {item["type"] for item in client.get("/api/v1/notifications").json()}
    _post(client, f"/api/v1/workflow/scenes/{scene['id']}/reject", {
        "stageKey": "layout_character", "comment": "比例需要修改", "workStepIds": [step["id"]],
    })

    current["user"] = artist
    assert "work_step_rejected" in {item["type"] for item in client.get("/api/v1/notifications").json()}
    current["user"] = producer
    response = client.get(f"/api/v1/progress/projects/{project.id}/work-steps")
    assert response.status_code == 200, response.text
    progress = response.json()
    assert progress["summary"]["totalScenes"] == 1
    assert progress["summary"]["overdueScenes"] == 1
    assert progress["summary"]["rejectionCount"] == 1
    assert progress["workloads"][0]["userId"] == artist.id
    blocker = next(item for item in progress["blockers"] if item["workStepId"] == step["id"])
    assert {"overdue", "needs_fix"} <= set(blocker["types"])
    assert blocker["sceneName"] == "SC-M5-001"

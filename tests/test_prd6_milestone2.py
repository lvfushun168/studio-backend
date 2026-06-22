from __future__ import annotations

import uuid

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import engine, get_db
from app.main import app
from app.models.project import Project, SceneGroup, UserProjectMembership
from app.models.user import User
from app.models.work_step import WorkStepEvent


@pytest.fixture
def milestone2_client():
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    suffix = uuid.uuid4().hex[:8]
    producer = User(username=f"m2_producer_{suffix}", display_name="M2 Producer", role="producer", is_active=True)
    director = User(username=f"m2_director_{suffix}", display_name="M2 Director", role="director", is_active=True)
    artist = User(username=f"m2_artist_{suffix}", display_name="M2 Artist", role="artist", is_active=True)
    other_artist = User(username=f"m2_other_{suffix}", display_name="M2 Other", role="artist", is_active=True)
    db.add_all([producer, director, artist, other_artist])
    db.flush()
    project = Project(name=f"M2 Project {suffix}", created_by=producer.id)
    db.add(project)
    db.flush()
    for user in (producer, director, artist, other_artist):
        db.add(UserProjectMembership(user_id=user.id, project_id=project.id, role_in_project=user.role))
    group = SceneGroup(project_id=project.id, name="M2 Group", sort_order=10)
    db.add(group)
    db.commit()
    current_user = {"value": producer}

    def override_db():
        yield db

    def override_user():
        return current_user["value"]

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    with TestClient(app) as client:
        yield client, db, current_user, producer, director, artist, other_artist, project, group
    app.dependency_overrides.clear()
    db.close()
    transaction.rollback()
    connection.close()


def _post(client, path, payload=None):
    response = client.post(path, json=payload or {})
    assert response.status_code in {200, 201, 204}, response.text
    return response


def _create_step_asset(client, project_id, group_id, scene_id, step, name):
    return _post(client, "/api/v1/assets", {
        "projectId": project_id,
        "sceneGroupId": group_id,
        "sceneId": scene_id,
        "stageKey": step["stageKey"],
        "sceneWorkStepId": step["id"],
        "assetUsage": "step_draft",
        "assetType": "original",
        "mediaType": "image",
        "originalName": name,
    }).json()


def test_step_transitions_submission_versions_and_stage_review_linkage(milestone2_client):
    client, db, current, producer, director, artist, other_artist, project, group = milestone2_client
    template = _post(client, "/api/v1/work-step-templates", {
        "scope": "project",
        "projectId": project.id,
        "name": "Layout 人物 M2",
        "stageKey": "layout_character",
        "isDefault": True,
        "items": [
            {"stepKey": "rough", "name": "草图", "sortOrder": 10},
            {"stepKey": "cleanup", "name": "清线", "sortOrder": 20},
        ],
    }).json()
    assert template["isDefault"] is True

    scene = _post(client, "/api/v1/scenes", {
        "projectId": project.id,
        "sceneGroupId": group.id,
        "name": "SC-M2-001",
        "stageTemplate": "standard",
        "pipeline": "standard",
    }).json()
    entry_asset = _post(client, "/api/v1/assets", {
        "projectId": project.id,
        "sceneGroupId": group.id,
        "sceneId": scene["id"],
        "stageKey": "storyboard",
        "assetUsage": "stage_asset",
        "assetType": "original",
        "mediaType": "image",
        "originalName": "storyboard.png",
    }).json()
    assert entry_asset["assetUsage"] == "stage_asset"
    _post(client, f"/api/v1/workflow/scenes/{scene['id']}/initialize-entry")

    steps = client.get(f"/api/v1/scenes/{scene['id']}/stages/layout_character/work-steps").json()
    assert [step["status"] for step in steps] == ["todo", "not_ready"]
    for step in steps:
        patched = client.patch(f"/api/v1/work-steps/{step['id']}", json={"assigneeId": artist.id})
        assert patched.status_code == 200, patched.text

    current["value"] = other_artist
    denied = client.post(f"/api/v1/work-steps/{steps[0]['id']}/start")
    assert denied.status_code == 403

    current["value"] = artist
    first = _post(client, f"/api/v1/work-steps/{steps[0]['id']}/start").json()
    assert first["status"] == "in_progress"
    first_asset = _create_step_asset(client, project.id, group.id, scene["id"], first, "rough-v1.png")
    submission_v1 = _post(client, f"/api/v1/work-steps/{first['id']}/submit", {
        "note": "rough v1",
        "assetIds": [first_asset["id"]],
    }).json()
    assert submission_v1["version"] == 1
    assert submission_v1["status"] == "submitted"

    refreshed = client.get(f"/api/v1/scenes/{scene['id']}/stages/layout_character/work-steps").json()
    assert [step["status"] for step in refreshed] == ["submitted", "todo"]
    early_review = client.post(f"/api/v1/workflow/scenes/{scene['id']}/submit", json={"stageKey": "layout_character"})
    assert early_review.status_code == 409

    withdrawn = _post(client, f"/api/v1/work-steps/{first['id']}/withdraw").json()
    assert withdrawn["status"] == "withdrawn"
    refreshed = client.get(f"/api/v1/scenes/{scene['id']}/stages/layout_character/work-steps").json()
    assert [step["status"] for step in refreshed] == ["in_progress", "not_ready"]

    submission_v2 = _post(client, f"/api/v1/work-steps/{first['id']}/submit", {
        "note": "rough v2",
        "assetIds": [first_asset["id"]],
    }).json()
    assert submission_v2["version"] == 2

    second = _post(client, f"/api/v1/work-steps/{steps[1]['id']}/start").json()
    second_asset = _create_step_asset(client, project.id, group.id, scene["id"], second, "cleanup-v1.png")
    _post(client, f"/api/v1/work-steps/{second['id']}/submit", {"assetIds": [second_asset["id"]]})
    _post(client, f"/api/v1/workflow/scenes/{scene['id']}/submit", {"stageKey": "layout_character"})

    blocked_withdraw = client.post(f"/api/v1/work-steps/{second['id']}/withdraw")
    assert blocked_withdraw.status_code == 409
    current["value"] = director
    _post(client, f"/api/v1/workflow/scenes/{scene['id']}/approve", {"stageKey": "layout_character"})
    approved_steps = client.get(f"/api/v1/scenes/{scene['id']}/stages/layout_character/work-steps").json()
    assert [step["status"] for step in approved_steps] == ["done", "done"]
    submissions = client.get(f"/api/v1/work-steps/{first['id']}/submissions").json()
    assert [(item["version"], item["status"]) for item in submissions] == [(2, "stage_accepted"), (1, "withdrawn")]

    current["value"] = producer
    bg_step = client.get(f"/api/v1/scenes/{scene['id']}/stages/layout_background/work-steps").json()[0]
    patched = client.patch(f"/api/v1/work-steps/{bg_step['id']}", json={"assigneeId": artist.id})
    assert patched.status_code == 200
    current["value"] = artist
    bg_step = _post(client, f"/api/v1/work-steps/{bg_step['id']}/start").json()
    bg_asset_v1 = _create_step_asset(client, project.id, group.id, scene["id"], bg_step, "background-v1.png")
    bg_submission_v1 = _post(client, f"/api/v1/work-steps/{bg_step['id']}/submit", {"assetIds": [bg_asset_v1["id"]]}).json()
    _post(client, f"/api/v1/workflow/scenes/{scene['id']}/submit", {"stageKey": "layout_background"})

    current["value"] = director
    rejected = _post(client, f"/api/v1/workflow/scenes/{scene['id']}/reject", {
        "stageKey": "layout_background",
        "comment": "透视需要修正",
        "workStepIds": [bg_step["id"]],
    }).json()
    assert rejected[0]["extraJson"]["workStepIds"] == [bg_step["id"]]
    assert client.get(f"/api/v1/work-steps/{bg_step['id']}").json()["status"] == "needs_fix"

    current["value"] = artist
    _post(client, f"/api/v1/work-steps/{bg_step['id']}/start")
    bg_asset_v2 = _create_step_asset(client, project.id, group.id, scene["id"], bg_step, "background-v2.png")
    bg_submission_v2 = _post(client, f"/api/v1/work-steps/{bg_step['id']}/submit", {"assetIds": [bg_asset_v2["id"]]}).json()
    assert bg_submission_v2["version"] == 2
    assert bg_submission_v1["version"] == 1
    _post(client, f"/api/v1/workflow/scenes/{scene['id']}/submit", {"stageKey": "layout_background"})
    current["value"] = director
    _post(client, f"/api/v1/workflow/scenes/{scene['id']}/approve", {"stageKey": "layout_background"})
    assert client.get(f"/api/v1/work-steps/{bg_step['id']}").json()["status"] == "done"

    scene_after = client.get(f"/api/v1/scenes/{scene['id']}").json()
    keyframe = next(item for item in scene_after["stageProgresses"] if item["stageKey"] == "keyframe")
    assert keyframe["status"] == "pending"
    keyframe_step = client.get(f"/api/v1/scenes/{scene['id']}/stages/keyframe/work-steps").json()[0]
    assert keyframe_step["status"] == "todo"
    current["value"] = producer
    cancelled = client.post(f"/api/v1/work-steps/{keyframe_step['id']}/cancel")
    assert cancelled.status_code == 204
    assert client.get(f"/api/v1/work-steps/{keyframe_step['id']}").json()["status"] == "cancelled"
    event_actions = set(
        db.scalars(
            select(WorkStepEvent.action).where(WorkStepEvent.scene_id == scene["id"])
        ).all()
    )
    assert {"step.start", "step.submit", "step.withdraw", "step.needs_fix", "step.complete", "step.unlock", "step.cancel"} <= event_actions

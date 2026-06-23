from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import event, select
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import engine, get_db
from app.main import app
from app.models.asset import Asset
from app.models.project import Episode, Project, SceneGroup, UserProjectMembership
from app.models.scene import StageProgress
from app.models.user import User
from app.models.work_step import SceneWorkStep, StepSubmission, StepSubmissionAsset


@pytest.fixture
def milestone3_client():
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    suffix = uuid.uuid4().hex[:8]
    producer = User(username=f"m3_producer_{suffix}", display_name="制片甲", role="producer", is_active=True)
    artist = User(username=f"m3_artist_{suffix}", display_name="画师乙", role="artist", is_active=True)
    db.add_all([producer, artist])
    db.flush()
    project = Project(name=f"M3 Project {suffix}", created_by=producer.id)
    db.add(project)
    db.flush()
    db.add_all([
        UserProjectMembership(user_id=producer.id, project_id=project.id, role_in_project="producer"),
        UserProjectMembership(user_id=artist.id, project_id=project.id, role_in_project="artist"),
    ])
    episode = Episode(project_id=project.id, episode_number=1, name="EP01")
    db.add(episode)
    db.flush()
    group = SceneGroup(project_id=project.id, episode_id=episode.id, name="A组", sort_order=10)
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
        yield client, db, current_user, producer, artist, project, episode, group, connection
    app.dependency_overrides.clear()
    db.close()
    transaction.rollback()
    connection.close()


def _create_scene(client, project_id, group_id, name):
    response = client.post("/api/v1/scenes", json={
        "projectId": project_id,
        "sceneGroupId": group_id,
        "name": name,
        "stageTemplate": "standard",
        "pipeline": "standard",
    })
    assert response.status_code == 201, response.text
    return response.json()


def test_matrix_task_query_batch_update_and_template_preview(milestone3_client):
    client, db, current, producer, artist, project, episode, group, connection = milestone3_client
    scene1 = _create_scene(client, project.id, group.id, "SC001")
    scene2 = _create_scene(client, project.id, group.id, "SC002")
    steps1 = client.get(f"/api/v1/scenes/{scene1['id']}/stages/layout_character/work-steps").json()
    target = steps1[0]
    due_at = datetime.now(timezone.utc) - timedelta(days=1)
    batch = client.post("/api/v1/work-steps/batch-update", json={
        "workStepIds": [target["id"]],
        "assigneeId": artist.id,
        "dueAt": due_at.isoformat(),
        "priority": "urgent",
        "blockedReason": "missing_reference",
        "note": "等待设定",
    })
    assert batch.status_code == 200, batch.text
    assert batch.json()[0]["assigneeId"] == artist.id

    work_step = db.get(SceneWorkStep, target["id"])
    progress = db.get(StageProgress, work_step.stage_progress_id)
    progress.status = "in_progress"
    work_step.status = "submitted"
    work_step.submitted_at = datetime.now(timezone.utc)
    asset = Asset(
        project_id=project.id,
        scene_group_id=group.id,
        scene_id=scene1["id"],
        stage_key="layout_character",
        scene_work_step_id=work_step.id,
        asset_usage="step_submission",
        lifecycle_status="submitted",
        asset_type="original",
        media_type="image",
        is_global=False,
        filename="layout.png",
        original_name="layout.png",
        storage_path="test/layout.png",
        public_url="/media/test/layout.png",
        thumbnail_url="/media/test/layout-thumb.png",
        version=1,
        uploaded_by=artist.id,
    )
    db.add(asset)
    db.flush()
    submission = StepSubmission(
        project_id=project.id,
        scene_id=scene1["id"],
        scene_work_step_id=work_step.id,
        stage_progress_id=progress.id,
        stage_key="layout_character",
        version=1,
        status="submitted",
        submitted_by=artist.id,
    )
    db.add(submission)
    db.flush()
    db.add(StepSubmissionAsset(submission_id=submission.id, asset_id=asset.id, sort_order=0))
    db.commit()

    query_count = {"value": 0}
    def count_query(*_):
        query_count["value"] += 1
    event.listen(connection, "before_cursor_execute", count_query)
    try:
        matrix_response = client.get("/api/v1/production-matrix", params={"project_id": project.id})
    finally:
        event.remove(connection, "before_cursor_execute", count_query)
    assert matrix_response.status_code == 200, matrix_response.text
    # Fixed query budget (includes the test fixture's SAVEPOINT bookkeeping),
    # independent of scene/stage count and therefore guards against N+1.
    assert query_count["value"] <= 14
    matrix = matrix_response.json()
    assert matrix["summary"]["sceneCount"] == 2
    assert matrix["sceneGroups"][0]["episodeId"] == episode.id
    cell = next(item for item in matrix["scenes"] if item["id"] == scene1["id"])["stageCells"]["layout_character"]
    assert cell["currentStep"]["assigneeName"] == artist.display_name
    assert cell["currentStep"]["priority"] == "urgent"
    assert cell["latestSubmission"]["version"] == 1
    assert cell["latestAsset"]["thumbnailUrl"] == "/media/test/layout-thumb.png"
    assert cell["flags"]["isOverdue"] is True
    assert cell["flags"]["hasBlocked"] is True

    overdue = client.get("/api/v1/production-matrix", params={"project_id": project.id, "overdue_only": True}).json()
    assert [item["id"] for item in overdue["scenes"]] == [scene1["id"]]
    task_response = client.get("/api/v1/work-steps", params={
        "project_id": project.id,
        "episode_id": episode.id,
        "assignee_id": artist.id,
        "blocked_only": True,
    })
    assert task_response.status_code == 200, task_response.text
    task = task_response.json()["items"][0]
    assert task["projectName"] == project.name
    assert task["episodeName"] == "EP01"
    assert task["sceneGroupName"] == "A组"
    assert task["sceneName"] == "SC001"
    assert task["latestSubmission"]["version"] == 1

    template_response = client.post("/api/v1/work-step-templates", json={
        "scope": "project",
        "projectId": project.id,
        "name": "一原标准步骤",
        "stageKey": "keyframe",
        "items": [
            {"stepKey": "rough_key", "name": "一原草稿", "sortOrder": 10},
            {"stepKey": "clean_key", "name": "一原清稿", "sortOrder": 20},
        ],
    })
    assert template_response.status_code == 201, template_response.text
    template = template_response.json()
    preview = client.post(
        f"/api/v1/scenes/{scene1['id']}/stages/keyframe/work-steps/apply-template",
        json={"templateId": template["id"], "mode": "replace", "previewOnly": True},
    )
    assert preview.status_code == 200, preview.text
    assert {item["stepKey"] for item in preview.json()["diff"]["add"]} == {"rough_key", "clean_key"}
    assert preview.json()["diff"]["cancel"][0]["stepKey"] == "stage_delivery"
    unchanged = client.get(f"/api/v1/scenes/{scene1['id']}/stages/keyframe/work-steps").json()
    assert [item["stepKey"] for item in unchanged] == ["stage_delivery"]

    batch_preview = client.post("/api/v1/work-steps/batch-apply-template", json={
        "templateId": template["id"],
        "mode": "replace",
        "previewOnly": True,
        "targets": [
            {"sceneId": scene1["id"], "stageKey": "keyframe"},
            {"sceneId": scene2["id"], "stageKey": "keyframe"},
        ],
    })
    assert batch_preview.status_code == 200, batch_preview.text
    assert batch_preview.json()["targetCount"] == 2
    applied = client.post("/api/v1/work-steps/batch-apply-template", json={
        "templateId": template["id"],
        "mode": "replace",
        "previewOnly": False,
        "targets": [
            {"sceneId": scene1["id"], "stageKey": "keyframe"},
            {"sceneId": scene2["id"], "stageKey": "keyframe"},
        ],
    })
    assert applied.status_code == 200, applied.text
    for scene in (scene1, scene2):
        active = client.get(f"/api/v1/scenes/{scene['id']}/stages/keyframe/work-steps").json()
        assert [item["stepKey"] for item in active] == ["rough_key", "clean_key"]

    current["value"] = artist
    denied = client.post("/api/v1/work-steps/batch-update", json={"workStepIds": [target["id"]], "priority": "low"})
    assert denied.status_code == 403

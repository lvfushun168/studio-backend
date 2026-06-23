from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.auth import get_current_user
from app.core.database import engine, get_db
from app.main import app
from app.models.annotation import Annotation
from app.models.asset import Asset
from app.models.project import Episode, Project, SceneAssignment, SceneGroup, UserProjectMembership
from app.models.scene import StageProgress
from app.models.user import User
from app.models.work_step import SceneWorkStep, StepSubmission, StepSubmissionAsset


@pytest.fixture
def milestone4_client():
    connection = engine.connect()
    transaction = connection.begin()
    db = Session(bind=connection, join_transaction_mode="create_savepoint")
    suffix = uuid.uuid4().hex[:8]
    producer = User(username=f"m4_producer_{suffix}", display_name="制片", role="producer", is_active=True)
    artist = User(username=f"m4_artist_{suffix}", display_name="画师", role="artist", is_active=True)
    db.add_all([producer, artist])
    db.flush()
    project = Project(name=f"M4 Project {suffix}", created_by=producer.id)
    db.add(project)
    db.flush()
    db.add_all([
        UserProjectMembership(user_id=producer.id, project_id=project.id, role_in_project="producer"),
        UserProjectMembership(user_id=artist.id, project_id=project.id, role_in_project="artist"),
    ])
    episode = Episode(project_id=project.id, episode_number=1, name="EP01")
    db.add(episode)
    db.flush()
    group = SceneGroup(project_id=project.id, episode_id=episode.id, name="A组")
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
        yield client, db, current, producer, artist, project, group
    app.dependency_overrides.clear()
    db.close()
    transaction.rollback()
    connection.close()


def _asset(db, *, project, group, producer, scene_id=None, stage_key="reference", step_id=None, usage="reference", name="file.png"):
    asset = Asset(
        project_id=project.id, scene_group_id=group.id, scene_id=scene_id, stage_key=stage_key,
        scene_work_step_id=step_id, asset_usage=usage, lifecycle_status="active", asset_type="original",
        media_type="image", is_global=False, filename=name, original_name=name, storage_path=f"test/{name}",
        public_url=f"/media/test/{name}", thumbnail_url=f"/media/test/thumb-{name}", version=1, uploaded_by=producer.id,
    )
    db.add(asset)
    db.flush()
    return asset


def test_my_tasks_inheritance_and_input_aggregation(milestone4_client):
    client, db, current, producer, artist, project, group = milestone4_client
    created = client.post("/api/v1/scenes", json={
        "projectId": project.id, "sceneGroupId": group.id, "name": "SC001",
        "stageTemplate": "standard", "pipeline": "standard",
    })
    assert created.status_code == 201, created.text
    scene_id = created.json()["id"]
    progress = db.query(StageProgress).filter_by(scene_id=scene_id, stage_key="layout_character").one()
    progress.status = "in_progress"
    progress.assignee_id = artist.id
    first = db.query(SceneWorkStep).filter_by(scene_id=scene_id, stage_key="layout_character").one()
    first.status = "submitted"
    target = SceneWorkStep(
        project_id=project.id, scene_group_id=group.id, scene_id=scene_id, stage_progress_id=progress.id,
        stage_key="layout_character", step_key="clean", name="清线", original_name="清线", sort_order=20,
        is_required=True, allow_parallel=False, status="todo", priority="normal", created_by=producer.id,
    )
    db.add(target)
    storyboard = db.query(StageProgress).filter_by(scene_id=scene_id, stage_key="storyboard").one()
    storyboard.status = "approved"
    group_ref = _asset(db, project=project, group=group, producer=producer, name="group.png")
    supplement = _asset(db, project=project, group=group, producer=producer, scene_id=scene_id, stage_key="layout_character", name="supplement.png")
    upstream = _asset(db, project=project, group=group, producer=producer, scene_id=scene_id, stage_key="storyboard", usage="step_submission", name="storyboard.png")
    previous = _asset(db, project=project, group=group, producer=producer, scene_id=scene_id, stage_key="layout_character", step_id=first.id, usage="step_submission", name="rough.png")
    submission = StepSubmission(
        project_id=project.id, scene_id=scene_id, scene_work_step_id=first.id, stage_progress_id=progress.id,
        stage_key="layout_character", version=1, status="submitted", submitted_by=artist.id,
    )
    db.add(submission)
    db.flush()
    db.add(StepSubmissionAsset(submission_id=submission.id, asset_id=previous.id, sort_order=0))
    db.commit()

    current["user"] = artist
    mine = client.get("/api/v1/work-steps", params={"mine_only": True, "status": "todo"})
    assert mine.status_code == 200, mine.text
    task = next(item for item in mine.json()["items"] if item["id"] == target.id)
    assert task["assigneeId"] == artist.id
    assert task["assigneeName"] == artist.display_name
    assert task["inputAssetCount"] == 4
    assert task["missingInput"] is False

    inputs = client.get(f"/api/v1/work-steps/{target.id}/input-assets")
    assert inputs.status_code == 200, inputs.text
    payload = inputs.json()
    assert [group["key"] for group in payload["groups"]] == [
        "scene_group_reference", "stage_supplement", "upstream_stage", "previous_work_step", "director_feedback",
    ]
    assert {asset["id"] for asset in payload["assets"]} == {group_ref.id, supplement.id, upstream.id, previous.id}
    assert payload["missingInput"] is False

    progress.assignee_id = None
    db.add(SceneAssignment(scene_id=scene_id, user_id=artist.id, stage_key="layout_character"))
    db.commit()
    inherited = client.get("/api/v1/work-steps", params={"mine_only": True, "status": "todo"}).json()["items"]
    assert any(item["id"] == target.id for item in inherited)


def test_missing_input_flags_and_feedback(milestone4_client):
    client, db, current, producer, artist, project, group = milestone4_client
    created = client.post("/api/v1/scenes", json={
        "projectId": project.id, "sceneGroupId": group.id, "name": "SC002",
        "stageTemplate": "standard", "pipeline": "standard",
    }).json()
    progress = db.query(StageProgress).filter_by(scene_id=created["id"], stage_key="keyframe").one()
    progress.status = "in_progress"
    progress.assignee_id = artist.id
    step = db.query(SceneWorkStep).filter_by(scene_id=created["id"], stage_key="keyframe").one()
    step.status = "needs_fix"
    output = _asset(db, project=project, group=group, producer=producer, scene_id=created["id"], stage_key="keyframe", step_id=step.id, usage="step_submission", name="keyframe.png")
    submission = StepSubmission(
        project_id=project.id, scene_id=created["id"], scene_work_step_id=step.id, stage_progress_id=progress.id,
        stage_key="keyframe", version=1, status="stage_rejected", submitted_by=artist.id, reject_reason="人物比例需要调整",
    )
    db.add(submission)
    db.flush()
    db.add(StepSubmissionAsset(submission_id=submission.id, asset_id=output.id))
    db.add(Annotation(
        project_id=project.id, target_asset_id=output.id, target_version=1, author_id=producer.id,
        author_role="director", canvas_json={"objects": []}, summary="手臂位置偏高",
    ))
    db.commit()
    current["user"] = artist
    payload = client.get(f"/api/v1/work-steps/{step.id}/input-assets").json()
    assert payload["missingInput"] is True
    assert "缺上游阶段文件" in payload["missingInputReasons"]
    assert {item["summary"] for item in payload["feedback"]} >= {"人物比例需要调整", "手臂位置偏高"}
    assert payload["submissions"][0]["assets"][0]["id"] == output.id

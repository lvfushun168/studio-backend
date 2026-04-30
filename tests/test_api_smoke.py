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


def test_non_admin_cannot_list_all_users(client: TestClient) -> None:
    response = client.get("/api/v1/users", headers={"X-User-ID": "5"})
    assert response.status_code == 403


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

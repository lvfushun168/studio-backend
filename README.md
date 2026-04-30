# Studio Asset System Backend

## Overview

This backend now targets the PRD5 collaboration workflow:

- multi-role project access (`admin/director/producer/artist/visitor`)
- scenes, stage progress, workflow review, notifications
- image/video asset upload, versioning, annotation artifacts
- bank materials and reference graph
- async jobs, worker execution, and project export

## Local Development

```bash
cd /Users/lvfushun/PycharmProjects/gemini_webapi
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
cp .env.example .env
```

Recommended local `.env` baseline:

```env
APP_ENV=development
DATABASE_URL=postgresql+psycopg://lvfushun@127.0.0.1:5432/studio_asset_system
MEDIA_ROOT=./storage
DEV_DEFAULT_USER_ID=
```

`DEV_DEFAULT_USER_ID` is optional. If unset, unauthenticated requests are rejected with `401`.

## Database Setup

Run migrations and seed demo data:

```bash
cd /Users/lvfushun/PycharmProjects/gemini_webapi/backend
../.venv/bin/alembic upgrade head
../.venv/bin/python scripts/seed_data.py
```

## Start API

```bash
cd /Users/lvfushun/PycharmProjects/gemini_webapi/backend
../.venv/bin/uvicorn app.main:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/api/v1/health
```

The health payload now includes:

- overall `status`
- `database.ok/detail`
- `storage.ok/detail`

## Start Worker

```bash
cd /Users/lvfushun/PycharmProjects/gemini_webapi/backend
../.venv/bin/python scripts/run_worker.py
```

The worker executes:

- `annotation_render`
- `video_thumbnail`
- `project_export`

## Authentication For Frontend / API Debugging

Two development-friendly modes are supported:

1. `X-User-ID`
   Example: `X-User-ID: 2`
2. `X-API-Key`

Example:

```bash
curl -H "X-User-ID: 2" http://127.0.0.1:8000/api/v1/projects
```

## Regression Verification

Full regression flow:

```bash
cd /Users/lvfushun/PycharmProjects/gemini_webapi/backend
../.venv/bin/pytest -q
../.venv/bin/python -m compileall app tests scripts
```

End-to-end migration + seed + regression verification:

```bash
cd /Users/lvfushun/PycharmProjects/gemini_webapi/backend
TEST_DB_URL="postgresql+psycopg://lvfushun@127.0.0.1:5432/studio_asset_system" ./scripts/verify_stack.sh
```

## Key API Areas

- `/api/v1/health`
- `/api/v1/system/bootstrap`
- `/api/v1/projects`
- `/api/v1/scenes`
- `/api/v1/workflow`
- `/api/v1/assets`
- `/api/v1/annotations`
- `/api/v1/bank`
- `/api/v1/references`
- `/api/v1/notifications`
- `/api/v1/async-jobs`

## Deployment Notes

- `docker-compose.yml` starts `postgres`, `backend`, and `nginx`
- media files are stored under `storage/`
- exports are generated under `storage/exports/`
- generated thumbnails / annotation artifacts are stored under `storage/generated/`

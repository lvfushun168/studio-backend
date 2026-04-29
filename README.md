# studio_asset_system Backend

## Overview

This backend has been rebuilt toward the new `studio_asset_system` architecture.
The current mainline is no longer centered on Gemini account pooling. The backend
now uses PostgreSQL as the primary datastore and provides the first formal domain
foundation for projects, scene groups, scenes, and stage progress.

## Local Development

```bash
cd /Users/lvfushun/PycharmProjects/gemini_webapi
python -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
cp .env.example .env
```

Current local PostgreSQL development baseline:

```env
DATABASE_URL=postgresql+psycopg://lvfushun@127.0.0.1:5432/studio_asset_system
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

## Start Worker

```bash
cd /Users/lvfushun/PycharmProjects/gemini_webapi/backend
../.venv/bin/python scripts/run_worker.py
```

## Alembic

Initialize the database with migrations once the first revision is created:

```bash
cd /Users/lvfushun/PycharmProjects/gemini_webapi/backend
../.venv/bin/alembic revision --autogenerate -m "initial schema"
../.venv/bin/alembic upgrade head
```

## Current API Surface

- `GET /api/v1/health`
- `GET /api/v1/system/bootstrap`
- `GET /api/v1/projects`
- `POST /api/v1/projects`
- `GET /api/v1/scenes`
- `POST /api/v1/scenes`

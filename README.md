# Gemini WebAPI Backend

## Quick Start

```bash
cd /Users/lvfushun/Downloads/8.148.146.195/gemini_webapi
source .venv/bin/activate
pip install -r backend/requirements.txt
cd backend
cp .env.example .env
python -m uvicorn app.main:app --reload
```

Health check:

```bash
curl http://127.0.0.1:8000/api/health
```

## Run Worker

```bash
cd /Users/lvfushun/Downloads/8.148.146.195/gemini_webapi/backend
../.venv/bin/python scripts/run_worker.py
```

## MySQL Example

```env
DATABASE_URL=mysql+pymysql://root:password@127.0.0.1:3306/gemini_webapi?charset=utf8mb4
COOKIE_ENCRYPTION_KEY=replace-this-in-production
MEDIA_ROOT=./storage
DEFAULT_MODEL=gemini-3-pro
```

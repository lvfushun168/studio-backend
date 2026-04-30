#!/bin/bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VENV_PYTHON="${VENV_PYTHON:-$ROOT_DIR/.venv/bin/python}"
VENV_ALEMBIC="${VENV_ALEMBIC:-$ROOT_DIR/.venv/bin/alembic}"
TEST_DB_URL="${TEST_DB_URL:-${DATABASE_URL:-}}"

if [ -z "$TEST_DB_URL" ]; then
  echo "TEST_DB_URL or DATABASE_URL must be set"
  exit 1
fi

export DATABASE_URL="$TEST_DB_URL"

echo "[1/4] Running migrations"
cd "$ROOT_DIR"
"$VENV_ALEMBIC" upgrade head

echo "[2/4] Seeding demo data"
"$VENV_PYTHON" scripts/seed_data.py

echo "[3/4] Running API regression tests"
"$ROOT_DIR/.venv/bin/pytest" -q

echo "[4/4] Compiling sources"
"$VENV_PYTHON" -m compileall app tests scripts

echo "Verification completed successfully."

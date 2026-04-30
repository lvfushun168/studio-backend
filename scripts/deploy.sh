#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "=== Studio Asset System Deployment ==="

# Backup database before deploy
echo "[1/4] Backing up database..."
mkdir -p backups
BACKUP_FILE="backups/db_$(date +%Y%m%d_%H%M%S).sql"
docker compose exec -T postgres pg_dump -U studio studio_asset_system > "$BACKUP_FILE" 2>/dev/null || echo "Backup skipped (DB may not be running)"

# Build and start
echo "[2/4] Building images..."
docker compose build backend

echo "[3/4] Starting services..."
docker compose up -d

# Run migrations
echo "[4/4] Running migrations..."
docker compose exec backend alembic upgrade head || echo "Migration step skipped"

echo "=== Deployment complete ==="

#!/bin/bash
set -e

cd "$(dirname "$0")/.."

echo "=== Rollback ==="
echo "Available backups:"
ls -lt backups/db_*.sql 2>/dev/null | head -5 || echo "No backups found"

if [ -z "$1" ]; then
    echo "Usage: $0 <backup_sql_file>"
    exit 1
fi

BACKUP_FILE="$1"

echo "Rolling back database from $BACKUP_FILE..."
docker compose exec -T postgres psql -U studio -d studio_asset_system < "$BACKUP_FILE"

echo "Rollback complete."

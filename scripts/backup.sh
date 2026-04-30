#!/bin/bash
set -e

cd "$(dirname "$0")/.."

BACKUP_DIR="backups"
mkdir -p "$BACKUP_DIR"

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
DB_BACKUP="$BACKUP_DIR/db_$TIMESTAMP.sql"
MEDIA_BACKUP="$BACKUP_DIR/media_$TIMESTAMP.tar.gz"

echo "Backing up database..."
docker compose exec -T postgres pg_dump -U studio studio_asset_system > "$DB_BACKUP"

echo "Backing up media files..."
tar -czf "$MEDIA_BACKUP" -C . storage/

echo "Backup complete:"
echo "  DB:   $DB_BACKUP"
echo "  Media: $MEDIA_BACKUP"

#!/bin/sh
set -eu

project_dir=${1:-/home/ubuntu/ops-dras}
backup_dir=${2:-$project_dir/backups}
retention_days=${BACKUP_RETENTION_DAYS:-14}

mkdir -p "$backup_dir"
cd "$project_dir"

timestamp=$(date +%Y%m%d-%H%M%S)
target="$backup_dir/ops-dras-$timestamp.sql.gz"
docker compose exec -T postgres pg_dump \
  -U "${POSTGRES_USER:-ops_dras}" "${POSTGRES_DB:-ops_dras}" | gzip > "$target"
test -s "$target"
find "$backup_dir" -type f -name 'ops-dras-*.sql.gz' -mtime "+$retention_days" -delete
echo "$target"

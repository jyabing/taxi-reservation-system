#!/bin/bash

# 载入 .env 中的变量
set -o allexport
source .env
set +o allexport

# === 配置参数（从 .env 中读取）===
DB_NAME="${DB_NAME}"
DB_USER="${DB_USER}"
DB_PASS="${DB_PASS}"
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"

# === 备份存储路径 ===
BACKUP_DIR="./backups"
DATE=$(date +%F)
BACKUP_FILE="${BACKUP_DIR}/${DB_NAME}_backup_${DATE}.sql"

# === 确保备份目录存在 ===
mkdir -p "$BACKUP_DIR"

# === 执行备份 ===
PGPASSWORD="$DB_PASS" pg_dump -U "$DB_USER" -h "$DB_HOST" -p "$DB_PORT" -d "$DB_NAME" > "$BACKUP_FILE"

# === 删除 7 天前的旧备份（可选）===
find "$BACKUP_DIR" -name "*.sql" -type f -mtime +7 -delete

echo "✅ Backup complete: $BACKUP_FILE"

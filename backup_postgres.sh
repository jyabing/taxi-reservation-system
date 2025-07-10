#!/bin/bash

# 加载 .env 环境变量
source /mnt/e/Django-project/taxi_project/.env

# 时间戳与保存目录
TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BACKUP_DIR="/mnt/e/Django-project/taxi_project/db_backups"
mkdir -p "$BACKUP_DIR"

# 构造连接字符串
DB_URL="postgresql://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"

# 执行备份（⚠️ 用引号包住 URL 防止特殊字符冲突）
pg_dump "$DB_URL" > "$BACKUP_DIR/db_backup_$TIMESTAMP.sql"

# 输出完成信息
echo "✅ 备份完成：$BACKUP_DIR/db_backup_$TIMESTAMP.sql"

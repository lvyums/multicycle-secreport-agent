#!/usr/bin/env bash
# 数据备份（V2.2 D1）— MySQL dump + reports/ + vector_data/ 归档，保留 N 天
# 用法: ./backup.sh [--keep 7]
# 定时: crontab -e  →  0 2 * * * /opt/sec-report-agent/sec_report_agent/scripts/dev/backup.sh >> /var/log/sec-report-backup.log 2>&1
set -euo pipefail

BACKUP_ROOT="${BACKUP_ROOT:-$(cd "$(dirname "$0")/../../.." && pwd)/backups}"
KEEP="${KEEP:-7}"
TS="$(date +%Y%m%d_%H%M%S)"
mkdir -p "$BACKUP_ROOT"

# MySQL 连接（可用环境变量覆盖）
MYSQL_HOST="${MYSQL_HOST:-127.0.0.1}"
MYSQL_PORT="${MYSQL_PORT:-3306}"
MYSQL_USER="${MYSQL_USER:-sec_report}"
MYSQL_PASS="${MYSQL_PASS:-sec_report_dev}"
MYSQL_DB="${MYSQL_DB:-sec_report}"

echo "[backup] $(date '+%F %T') 开始备份 → $BACKUP_ROOT"

# 1) 数据库
mysqldump --single-transaction --quick \
  -h"$MYSQL_HOST" -P"$MYSQL_PORT" -u"$MYSQL_USER" -p"$MYSQL_PASS" "$MYSQL_DB" \
  | gzip > "$BACKUP_ROOT/sec_report_${TS}.sql.gz"
echo "[backup] 数据库归档: sec_report_${TS}.sql.gz ($(du -h "$BACKUP_ROOT/sec_report_${TS}.sql.gz" | cut -f1))"

# 2) 文件卷（报告/向量库）
WORKDIR="$(cd "$(dirname "$0")/../.." && pwd)"
if [ -d "$WORKDIR/reports" ] || [ -d "$WORKDIR/vector_data" ]; then
  tar -czf "$BACKUP_ROOT/files_${TS}.tar.gz" \
    -C "$WORKDIR" reports vector_data 2>/dev/null || true
  echo "[backup] 文件归档: files_${TS}.tar.gz ($(du -h "$BACKUP_ROOT/files_${TS}.tar.gz" | cut -f1))"
fi

# 3) 保留策略：仅保留最近 N 天
find "$BACKUP_ROOT" -name '*.gz' -mtime +"$KEEP" -delete
echo "[backup] 完成（保留 ${KEEP} 天）"

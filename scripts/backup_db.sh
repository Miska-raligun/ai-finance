#!/bin/bash
# scripts/backup_db.sh — SQLite 一致性备份 + 滚动清理。
#
# 用 sqlite3 .backup 而非裸 cp：会获取 SQLite 的内部锁，确保即便正在被
# Waitress 写入也能拿到一致快照。
#
# 用法：
#   scripts/backup_db.sh            # 默认备份 backend/records.db → backend/logs/backups/
#   scripts/backup_db.sh /path/db   # 指定其他 DB 文件
#
# 定时（推荐每日 03:00）crontab 一行：
#   0 3 * * * cd /path/to/ai-finance && scripts/backup_db.sh >> logs/backup.log 2>&1
#
# 默认保留 14 份；超出按修改时间删最旧。
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
DB_PATH="${1:-$REPO_ROOT/backend/records.db}"
BACKUP_DIR="${BACKUP_DIR:-$REPO_ROOT/backend/logs/backups}"
KEEP="${BACKUP_KEEP:-14}"

if [[ ! -f "$DB_PATH" ]]; then
  echo "[backup] ❌ DB 文件不存在：$DB_PATH" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"

TS=$(date +%Y%m%d-%H%M%S)
DEST="$BACKUP_DIR/records-${TS}.db"

echo "[backup] 备份 $DB_PATH → $DEST"
sqlite3 "$DB_PATH" ".backup '$DEST'"

# 验证：能读 schema_version 即视为一致
if ! sqlite3 "$DEST" "SELECT COUNT(*) FROM schema_version" >/dev/null 2>&1; then
  echo "[backup] ⚠️ 备份文件可读但 schema_version 表查询失败，保留供检查"
fi

# 滚动清理：保留 KEEP 份最新
EXCESS=$(ls -1t "$BACKUP_DIR"/records-*.db 2>/dev/null | tail -n +$((KEEP + 1)) || true)
if [[ -n "$EXCESS" ]]; then
  echo "[backup] 清理超出 $KEEP 份的旧备份："
  echo "$EXCESS" | while read -r old; do
    echo "  删除 $old"
    rm -f "$old"
  done
fi

SIZE=$(du -h "$DEST" | cut -f1)
echo "[backup] ✅ 完成，大小 $SIZE，当前共 $(ls -1 "$BACKUP_DIR"/records-*.db | wc -l) 份"

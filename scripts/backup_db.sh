#!/bin/bash
# ZURK Database Backup
#
# Safely copies the SQLite database using sqlite3 .backup (prevents corruption
# from WAL mode or concurrent writes). Keeps the last 7 days of backups.
#
# Usage:
#   ./scripts/backup_db.sh          # Run backup
#   ./scripts/backup_db.sh --list   # List existing backups

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DB_FILE="$PROJECT_DIR/data/agent_center.db"
BACKUP_DIR="$PROJECT_DIR/backups"
LOG_FILE="$PROJECT_DIR/logs/backup.log"
RETENTION_DAYS=7

mkdir -p "$BACKUP_DIR" "$PROJECT_DIR/logs"

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $1" | tee -a "$LOG_FILE"
}

if [ "$1" = "--list" ]; then
    echo "ZURK Database Backups:"
    echo "──────────────────────"
    ls -lh "$BACKUP_DIR"/agent_center_*.db 2>/dev/null || echo "  No backups found."
    echo ""
    echo "Total: $(ls "$BACKUP_DIR"/agent_center_*.db 2>/dev/null | wc -l | tr -d ' ') backup(s)"
    exit 0
fi

if [ ! -f "$DB_FILE" ]; then
    log "[SKIP] Database not found at $DB_FILE"
    exit 0
fi

TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/agent_center_${TIMESTAMP}.db"

# Use sqlite3 .backup for a consistent snapshot (safe with WAL mode)
if command -v sqlite3 &>/dev/null; then
    sqlite3 "$DB_FILE" ".backup '$BACKUP_FILE'"
else
    # Fallback to cp if sqlite3 not available
    cp "$DB_FILE" "$BACKUP_FILE"
fi

if [ -f "$BACKUP_FILE" ]; then
    SIZE=$(ls -lh "$BACKUP_FILE" | awk '{print $5}')
    log "[OK] Backup created: $(basename "$BACKUP_FILE") ($SIZE)"
else
    log "[FAIL] Backup failed!"
    exit 1
fi

# Prune old backups
DELETED=$(find "$BACKUP_DIR" -name "agent_center_*.db" -mtime +${RETENTION_DAYS} -print -delete 2>/dev/null | wc -l | tr -d ' ')
if [ "$DELETED" -gt 0 ]; then
    log "[PRUNE] Removed $DELETED backup(s) older than $RETENTION_DAYS days."
fi

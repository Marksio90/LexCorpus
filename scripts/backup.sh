#!/usr/bin/env bash
# backup.sh — Backup PostgreSQL and Qdrant data
#
# Usage:
#   ./scripts/backup.sh                    # backup to ./backups/
#   BACKUP_DIR=/mnt/nas ./scripts/backup.sh
#
# Add to cron for nightly backups:
#   0 2 * * * /opt/lexcorpus/scripts/backup.sh >> /var/log/lexcorpus-backup.log 2>&1

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
KEEP_DAYS="${KEEP_DAYS:-7}"

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
info()  { echo -e "${GREEN}[$(date +%H:%M:%S)] BACKUP${NC} $*"; }
warn()  { echo -e "${YELLOW}[$(date +%H:%M:%S)] WARN${NC}   $*"; }
error() { echo -e "${RED}[$(date +%H:%M:%S)] ERROR${NC}  $*"; exit 1; }

mkdir -p "$BACKUP_DIR"

# ── 1. PostgreSQL ──────────────────────────────────────────────────────────────
info "Backing up PostgreSQL…"
PG_BACKUP="$BACKUP_DIR/postgres_${TIMESTAMP}.sql.gz"

if docker exec lexcorpus-postgres pg_dumpall -U "${POSTGRES_USER:-lexcorpus}" 2>/dev/null | \
    gzip > "$PG_BACKUP"; then
    SIZE=$(du -sh "$PG_BACKUP" | cut -f1)
    info "PostgreSQL backup: $PG_BACKUP ($SIZE)"
else
    warn "PostgreSQL backup failed — is the container running?"
fi

# ── 2. Qdrant ─────────────────────────────────────────────────────────────────
info "Backing up Qdrant storage…"
QDRANT_BACKUP="$BACKUP_DIR/qdrant_${TIMESTAMP}.tar.gz"

if [ -d "./data/qdrant" ]; then
    tar -czf "$QDRANT_BACKUP" ./data/qdrant/ 2>/dev/null
    SIZE=$(du -sh "$QDRANT_BACKUP" | cut -f1)
    info "Qdrant backup: $QDRANT_BACKUP ($SIZE)"
else
    warn "data/qdrant not found — skipping Qdrant backup"
fi

# ── 3. Remove old backups ─────────────────────────────────────────────────────
info "Removing backups older than ${KEEP_DAYS} days…"
find "$BACKUP_DIR" -name "*.sql.gz" -mtime "+${KEEP_DAYS}" -delete
find "$BACKUP_DIR" -name "*.tar.gz" -mtime "+${KEEP_DAYS}" -delete

info "Backup complete. Files in $BACKUP_DIR:"
ls -lh "$BACKUP_DIR" | tail -10

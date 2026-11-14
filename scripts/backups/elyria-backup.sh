#!/usr/bin/env bash
# Elyria nightly backup.  Usage:  elyria-backup.sh uat   (or: prod)
#
# Every night:  database dump + private files + media  ->  Hetzner Storage Box (encrypted), kept 14 days
# Sundays:      the same files also                    ->  Backblaze B2 (encrypted), kept 8 weeks
# Run as root (cron). Needs: postgres client tools, rclone remotes "boxcrypt" and "b2crypt" (see setup notes).
# Never deletes anything on the server except its own temporary copies.

set -euo pipefail

ENVIRONMENT="${1:?Usage: elyria-backup.sh uat|prod}"

# ---- Settings: fill these in once per environment ---------------------------------------------
case "$ENVIRONMENT" in
  uat)
    DB_NAME="CHANGE_ME_uat_db_name"
    PRIVATE_DIR="/srv/elyria/private/uat"
    MEDIA_DIR="/srv/elyria/media/uat"
    PING_URL=""            # optional: healthchecks.io ping URL for UAT
    ;;
  prod)
    DB_NAME="CHANGE_ME_prod_db_name"
    PRIVATE_DIR="/srv/elyria/private/prod"
    MEDIA_DIR="/srv/elyria/media/prod"
    PING_URL=""            # recommended: healthchecks.io ping URL for live
    ;;
  *) echo "Unknown environment: $ENVIRONMENT" >&2; exit 2 ;;
esac

BOX_KEEP_DAYS=14
B2_KEEP_DAYS=56
WEEKLY_DAY=7               # 1 = Monday ... 7 = Sunday
LOCAL_DIR="/var/backups/elyria/$ENVIRONMENT"
LOG="/var/log/elyria-backup.log"

# Server-only settings, one file per environment (not in git): DB_NAME, PING_URL
[ -f "/etc/elyria-backup-$ENVIRONMENT.conf" ] && . "/etc/elyria-backup-$ENVIRONMENT.conf"
# -----------------------------------------------------------------------------------------------

STAMP="$(date +%F_%H%M)"
WORK="$LOCAL_DIR/$STAMP"

log() { echo "$(date '+%F %T') [$ENVIRONMENT] $*" | tee -a "$LOG"; }

fail() {
  log "FAILED: ${1:-see above}"
  [ -n "$PING_URL" ] && curl -fsS -m 10 --retry 3 "$PING_URL/fail" >/dev/null || true
  exit 1
}
trap 'fail "line $LINENO"' ERR

[ -n "$PING_URL" ] && curl -fsS -m 10 --retry 3 "$PING_URL/start" >/dev/null || true
mkdir -p "$WORK"
chmod 700 "$LOCAL_DIR"
log "Starting backup -> $WORK"

# 1. Database (custom format: compressed, restores with pg_restore)
runuser -u postgres -- pg_dump -Fc "$DB_NAME" > "$WORK/db.dump"
log "Database dumped ($(du -h "$WORK/db.dump" | cut -f1))"

# 2. Files (private: Elite documents, member photos; media: site documents and public uploads)
tar -czf "$WORK/private.tar.gz" -C "$(dirname "$PRIVATE_DIR")" "$(basename "$PRIVATE_DIR")"
tar -czf "$WORK/media.tar.gz"   -C "$(dirname "$MEDIA_DIR")"   "$(basename "$MEDIA_DIR")"
log "Files packed (private $(du -h "$WORK/private.tar.gz" | cut -f1), media $(du -h "$WORK/media.tar.gz" | cut -f1))"

# 3. Nightly copy to the Storage Box (encrypted by rclone before it leaves the server)
rclone copy "$WORK" "boxcrypt:$ENVIRONMENT/$STAMP" --log-level ERROR
rclone delete "boxcrypt:$ENVIRONMENT" --min-age "${BOX_KEEP_DAYS}d" --log-level ERROR
rclone rmdirs "boxcrypt:$ENVIRONMENT" --leave-root --log-level ERROR || true
log "Copied to Storage Box (keeping $BOX_KEEP_DAYS days)"

# 4. Weekly copy outside Hetzner (Backblaze B2, encrypted)
if [ "$(date +%u)" = "$WEEKLY_DAY" ]; then
  rclone copy "$WORK" "b2crypt:$ENVIRONMENT/$STAMP" --log-level ERROR
  rclone delete "b2crypt:$ENVIRONMENT" --min-age "${B2_KEEP_DAYS}d" --log-level ERROR
  rclone rmdirs "b2crypt:$ENVIRONMENT" --leave-root --log-level ERROR || true
  log "Weekly copy sent to Backblaze B2 (keeping $B2_KEEP_DAYS days)"
fi

# 5. Keep only the last 2 local copies (the off-server copies are the real backups)
ls -1dt "$LOCAL_DIR"/*/ 2>/dev/null | tail -n +3 | xargs -r rm -rf

log "Backup finished OK"
[ -n "$PING_URL" ] && curl -fsS -m 10 --retry 3 "$PING_URL" >/dev/null || true
#!/usr/bin/env bash
# Noční záloha Štítků: konzistentní kopie SQLite (online backup API) + všechny soubory (fotky, PDF).
# Cron:  30 2 * * * /opt/stitky/deploy/backup.sh >> /var/log/stitky-backup.log 2>&1
# Zálohy jsou v /opt/stitky-backup, drží se 30 dní. Pro ochranu před ztrátou serveru
# je kopírujte i mimo VPS (Hetzner Storage Box, rclone apod.).
set -euo pipefail
DEST=/opt/stitky-backup
STAMP=$(date +%F)
mkdir -p "$DEST"

docker exec stitky mkdir -p /data/files   # na čerstvé instalaci ještě nic nenahráno
docker exec stitky python -c "
import sqlite3
src = sqlite3.connect('/data/app.db'); dst = sqlite3.connect('/data/backup-app.db')
src.backup(dst); dst.close(); src.close()"
docker exec stitky tar czf - -C /data backup-app.db files > "$DEST/stitky-$STAMP.tar.gz"
docker exec stitky rm -f /data/backup-app.db

find "$DEST" -name 'stitky-*.tar.gz' -mtime +30 -delete
echo "$(date '+%F %T') OK $(du -h "$DEST/stitky-$STAMP.tar.gz" | cut -f1)"

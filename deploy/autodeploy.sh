#!/usr/bin/env bash
# Auto-deploy Štítky: při novém commitu na origin/main srovná pracovní strom a přestaví kontejner.
# Cron:  */5 * * * * /opt/stitky/deploy/autodeploy.sh >> /var/log/stitky-autodeploy.log 2>&1
# Porovnává se s posledním ÚSPĚŠNÝM deployem (.last_deployed), ne s HEAD – při selhání buildu
# se tak deploy zkusí znovu (stejná poučka jako u NapojSiSám).
# Tělo je v závorce, aby `git reset` nepřepsal skript během běhu.
{
set -uo pipefail
REPO=/opt/stitky
STAMP="$REPO/.last_deployed"
log() { echo "$(date '+%F %T') $*"; }

cd "$REPO" || { log "!!! $REPO neexistuje"; exit 1; }
exec 9>"$REPO/.autodeploy.lock"
flock -n 9 || exit 0

git fetch origin main --quiet || { log "!!! git fetch selhal"; exit 1; }
REMOTE=$(git rev-parse origin/main)
[ -f "$STAMP" ] && [ "$(cat "$STAMP")" = "$REMOTE" ] && exit 0

log "Deploy $REMOTE"
git reset --hard origin/main --quiet
if docker compose up -d --build; then
    echo "$REMOTE" > "$STAMP"
    docker image prune -f >/dev/null
    log "OK"
else
    log "!!! build selhal – zkusím při dalším běhu"
    exit 1
fi
}

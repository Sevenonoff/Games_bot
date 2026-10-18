#!/usr/bin/env bash
# Выкладка бота Max на продовый сервер (запускать локально из любой папки).
#   ./max_bot/deploy/deploy.sh          — код + пересборка образа + перезапуск контейнера
#   ./max_bot/deploy/deploy.sh --env    — то же и скопировать локальный max_bot/.env
# Бот работает в контейнере games-bot (max_bot/deploy/compose.yaml) в сети china-cars: Caddy china-cars
# проксирует на него /hooks/games/<секрет>. Перезапуск после падения и перезагрузки — restart: unless-stopped.
# Каждое действие на сервере пишется в ~/claude-ops.log.
set -euo pipefail

HOST="${DEPLOY_HOST:-drom_root_user@91.227.18.215}"
KEY="${DEPLOY_KEY:-$HOME/.ssh/china_drom_ed25519}"
REMOTE_DIR="games_bot"
REPO="$(cd "$(dirname "$0")/../.." && pwd)"
SSH=(ssh -i "$KEY" -o IdentitiesOnly=yes "$HOST")
REV="$(git -C "$REPO" rev-parse --short HEAD 2>/dev/null || echo unknown)"
DIRTY="$(git -C "$REPO" status --porcelain -- games_core max_bot 2>/dev/null | grep -q . && echo "+dirty" || true)"

log_remote() { "${SSH[@]}" "echo \"\$(date -Is) [games_bot] $1\" >> ~/claude-ops.log"; }

log_remote "deploy start rev=$REV$DIRTY"

rsync -az --delete -e "ssh -i $KEY -o IdentitiesOnly=yes" \
    --exclude '__pycache__' --exclude '.env' --exclude 'data/' \
    "$REPO/games_core" "$REPO/max_bot" "$HOST:$REMOTE_DIR/"
log_remote "rsync games_core max_bot -> ~/$REMOTE_DIR"

if [[ "${1:-}" == "--env" ]]; then
    "${SSH[@]}" "umask 077 && cat > ~/$REMOTE_DIR/max_bot/.env" < "$REPO/max_bot/.env"
    log_remote "copied max_bot/.env (600)"
fi

"${SSH[@]}" bash -s <<EOF
set -euo pipefail
log() { echo "\$(date -Is) [games_bot] \$1" >> ~/claude-ops.log; echo "\$1"; }
cd ~/$REMOTE_DIR
echo "$REV$DIRTY" > REVISION
mkdir -p max_bot/data logs

# переход со старой схемы (venv + cron-сторож): снять cron и остановить процесс, если они ещё есть
if crontab -l 2>/dev/null | grep -q "$REMOTE_DIR/max_bot/deploy/botctl.sh"; then
    crontab -l | grep -v "$REMOTE_DIR/max_bot/deploy/botctl.sh" | crontab - || crontab -r
    log "crontab: removed legacy botctl watchdog"
fi
if pkill -u "\$(id -u)" -f "^\$HOME/$REMOTE_DIR/.venv/bin/python -m max_bot.main"; then
    sleep 2; log "stopped legacy venv bot"
fi

BOT_UID=\$(id -u) BOT_GID=\$(id -g) docker compose -f max_bot/deploy/compose.yaml up -d --build --quiet-pull 2>&1 | tail -n 3
log "compose up --build rev=$REV$DIRTY"
docker image prune -f --filter label=app=games-bot >/dev/null
sleep 5
docker compose -f max_bot/deploy/compose.yaml ps --format '{{.Name}} {{.Status}}'
tail -n 3 logs/max_bot.log
EOF

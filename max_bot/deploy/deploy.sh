#!/usr/bin/env bash
# Выкладка бота Max на продовый сервер (запускать локально из любой папки).
#   ./max_bot/deploy/deploy.sh          — код + зависимости + перезапуск
#   ./max_bot/deploy/deploy.sh --env    — то же и скопировать локальный max_bot/.env
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
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; log "created venv"; fi
.venv/bin/pip install -q --disable-pip-version-check -r max_bot/requirements.txt
log "pip install -r max_bot/requirements.txt"
chmod +x max_bot/deploy/botctl.sh
mkdir -p max_bot/data logs
CTL="\$HOME/$REMOTE_DIR/max_bot/deploy/botctl.sh"
( crontab -l 2>/dev/null | grep -v "$REMOTE_DIR/max_bot/deploy/botctl.sh" || true
  echo "* * * * * \$CTL start cron >/dev/null 2>&1"
  echo "@reboot \$CTL start reboot >/dev/null 2>&1" ) | crontab -
log "crontab: watchdog + @reboot"
max_bot/deploy/botctl.sh restart deploy
log "restart rev=$REV$DIRTY"
max_bot/deploy/botctl.sh status
EOF

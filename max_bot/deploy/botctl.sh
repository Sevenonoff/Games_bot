#!/usr/bin/env bash
# Управление ботом Max на сервере: start | stop | restart | status.
# start идемпотентен (flock), поэтому им же пользуется cron-сторож:
#   * * * * * ~/games_bot/max_bot/deploy/botctl.sh start
set -euo pipefail

APP_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
VENV="$APP_DIR/.venv"
LOG_DIR="$APP_DIR/logs"
LOCK="$LOG_DIR/max_bot.lock"
OUT="$LOG_DIR/max_bot.out"
PATTERN="^$VENV/bin/python -m max_bot.main"

mkdir -p "$LOG_DIR"

is_running() { pgrep -u "$(id -u)" -f "$PATTERN" >/dev/null; }

start() {
    if is_running; then return 0; fi
    cd "$APP_DIR"
    # flock -n: если бот уже держит lock, второй экземпляр сразу выходит
    LOG_FILE="$LOG_DIR/max_bot.log" nohup flock -n "$LOCK" "$VENV/bin/python" -m max_bot.main >>"$OUT" 2>&1 &
    sleep 2
    if is_running; then echo "started"; else echo "failed, see $OUT"; tail -n 20 "$OUT"; return 1; fi
}

stop() {
    if ! is_running; then echo "not running"; return 0; fi
    pkill -u "$(id -u)" -f "$PATTERN" || true
    for _ in $(seq 10); do is_running || { echo "stopped"; return 0; }; sleep 1; done
    pkill -9 -u "$(id -u)" -f "$PATTERN" || true
    echo "killed"
}

status() {
    if is_running; then
        pgrep -u "$(id -u)" -af "$PATTERN"
        ps -o rss=,etime= -p "$(pgrep -u "$(id -u)" -f "$PATTERN" | head -1)" | awk '{printf "rss=%d MB uptime=%s\n", $1/1024, $2}'
    else
        echo "not running"
    fi
}

case "${1:-status}" in
    start) start ;;
    stop) stop ;;
    restart) stop; start ;;
    status) status ;;
    *) echo "usage: $0 start|stop|restart|status"; exit 2 ;;
esac

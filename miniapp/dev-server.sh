#!/usr/bin/env bash
# Dev-сервер Mini App без Telegram: вход dev_user с localhost, подсказки ходов /dev/hint, своя БД.
# Боевому боту не мешает (не поллит Telegram, порт 8448). Подробности — sea_fight_aiogram/webapp_dev.py.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
exec "$ROOT/.venv/bin/python" "$ROOT/sea_fight_aiogram/webapp_dev.py" "$@"

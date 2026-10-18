import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

MAX_BOT_TOKEN = os.getenv("MAX_BOT_TOKEN")
DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "data" / "games.db"))
LOG_FILE = os.getenv("LOG_FILE", "")          # пусто — только stdout
PREVIEW_SECONDS = float(os.getenv("PREVIEW_SECONDS", "1.0"))
ROUND_SECONDS = int(os.getenv("ROUND_SECONDS", "60"))
COUNTDOWN_SECONDS = float(os.getenv("COUNTDOWN_SECONDS", "2.0"))
TIMER_TICK_SECONDS = float(os.getenv("TIMER_TICK_SECONDS", "5.0"))
MEMO_CLOSE_SECONDS = float(os.getenv("MEMO_CLOSE_SECONDS", "3.0"))
REVIEW_SECONDS = float(os.getenv("REVIEW_SECONDS", "2.0"))
# webhook: пусто — long polling. URL публичный (Caddy china-drom.ru → контейнер games-bot), путь содержит секрет;
# тот же секрет Max присылает в заголовке X-Max-Bot-Api-Secret
WEBHOOK_URL = os.getenv("WEBHOOK_URL", "")
WEBHOOK_SECRET = os.getenv("WEBHOOK_SECRET", "")
WEBHOOK_HOST = os.getenv("WEBHOOK_HOST", "0.0.0.0")
WEBHOOK_PORT = int(os.getenv("WEBHOOK_PORT", "8445"))
# кому доступны /dbg-команды: user_id через запятую; свой id бот покажет в ответ на /dbg
DEBUG_USER_IDS = frozenset(int(x) for x in os.getenv("DEBUG_USER_IDS", "").replace(",", " ").split())

PLATFORM = "max"

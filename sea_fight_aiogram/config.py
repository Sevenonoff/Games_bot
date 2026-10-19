import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN")
LOG_FILE = os.getenv("LOG_FILE", "")          # пусто — только stdout

# Все игры — ядро games_core: уровни, рекорды, рейтинг и бои с другом в SQLite, platform="tg"
GAMES_DB_PATH = os.getenv("GAMES_DB_PATH", str(BASE_DIR / "data" / "games.db"))
PREVIEW_SECONDS = float(os.getenv("PREVIEW_SECONDS", "1.0"))
ROUND_SECONDS = int(os.getenv("ROUND_SECONDS", "60"))
COUNTDOWN_SECONDS = float(os.getenv("COUNTDOWN_SECONDS", "2.0"))
TIMER_TICK_SECONDS = float(os.getenv("TIMER_TICK_SECONDS", "5.0"))
MEMO_CLOSE_SECONDS = float(os.getenv("MEMO_CLOSE_SECONDS", "3.0"))
REVIEW_SECONDS = float(os.getenv("REVIEW_SECONDS", "2.0"))
MP_BLINK_SECONDS = float(os.getenv("MP_BLINK_SECONDS", "0.4"))   # мигание потопленного корабля в бою с другом
# кому доступны /dbg-команды: user_id через запятую; свой id бот покажет в ответ на /dbg
DEBUG_USER_IDS = frozenset(int(x) for x in os.getenv("DEBUG_USER_IDS", "").replace(",", " ").split())

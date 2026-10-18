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
# кому доступны /dbg-команды: user_id через запятую; свой id бот покажет в ответ на /dbg
DEBUG_USER_IDS = frozenset(int(x) for x in os.getenv("DEBUG_USER_IDS", "").replace(",", " ").split())

PLATFORM = "max"

import os
from pathlib import Path

from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN")
LOG_FILE = os.getenv("LOG_FILE", "")          # пусто — только stdout

# Игры ядра games_core (мемо, матрица, башня): прогресс и рекорды в SQLite, platform="tg"
GAMES_DB_PATH = os.getenv("GAMES_DB_PATH", str(BASE_DIR / "data" / "games.db"))
PREVIEW_SECONDS = float(os.getenv("PREVIEW_SECONDS", "1.0"))
ROUND_SECONDS = int(os.getenv("ROUND_SECONDS", "60"))
COUNTDOWN_SECONDS = float(os.getenv("COUNTDOWN_SECONDS", "2.0"))
TIMER_TICK_SECONDS = float(os.getenv("TIMER_TICK_SECONDS", "5.0"))
MEMO_CLOSE_SECONDS = float(os.getenv("MEMO_CLOSE_SECONDS", "3.0"))
REVIEW_SECONDS = float(os.getenv("REVIEW_SECONDS", "2.0"))
# кому доступны /dbg-команды: user_id через запятую; свой id бот покажет в ответ на /dbg
DEBUG_USER_IDS = frozenset(int(x) for x in os.getenv("DEBUG_USER_IDS", "").replace(",", " ").split())

# Database configuration
DB_CONFIG = {
    "host": os.getenv("DB_HOST", "localhost"),
    "port": int(os.getenv("DB_PORT", 5432)),
    "database": os.getenv("DB_NAME", "seafight_bot"),
    "user": os.getenv("DB_USER", "postgres"),
    "password": os.getenv("DB_PASSWORD"),
}

# Game settings
ROWS = 8
COLS = 8
DELAY = 0.4

# Board symbols
EMPTY = ' 🟦 '
AVAILABLE = ' 🟩 '
SHIP = ' 🔳 '
BUILDING_SHIP = ' 🔲 '
BANG = ' 💥 '
BIGBANG = ' 💢 '
MISS = ' 💠 '

# Ship configurations
SHIPS = [4, 3, 3, 2, 2, 2, 1, 1, 1, 1]
SHIPS_REDUCED = [3, 2, 2, 1, 1, 1]

# Bot settings
ADMINS = []  # Add admin IDs here

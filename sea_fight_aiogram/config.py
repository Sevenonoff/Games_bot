import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")

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

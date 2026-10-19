"""Разовый перенос данных aiogram-версии (до 2.0.0, PostgreSQL) в SQLite ядра games_core.

Переносятся:
  users            → users (platform="tg"), имя — как в таблицах: username → имя → id;
  player_ratings   → ratings (mp_full / mp_reduced: рейтинг Elo, победы, поражения);
  leaderboard      → scores + progress.best_score (solo_full → sea_full, solo_reduced → sea_reduced).
Очки одиночного боя считались так же, как в ядре (+10 попадание, −1 промах), — рекорды сравнимы.
Незаконченные бои с другом не переносятся (на момент перехода их не было). Postgres не меняется.

Запуск при остановленном боте, из папки sea_fight_aiogram:
    systemctl --user stop games-tg-bot
    .venv/bin/python deploy/migrate_postgres.py          # повторный запуск откажется: данные уже есть
    systemctl --user start games-tg-bot
"""
import asyncio
import os
import sys
from pathlib import Path

import asyncpg

BOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BOT_DIR))
sys.path.append(str(BOT_DIR.parent))
import config  # noqa: E402  (заодно читает .env с DB_*)
from games_core.storage import Storage  # noqa: E402
from games_menu import PLATFORM, format_player_name  # noqa: E402

SOLO_GAMES = {"solo_full": "sea_full", "solo_reduced": "sea_reduced"}


async def fetch_all():
    conn = await asyncpg.connect(host=os.getenv("DB_HOST", "localhost"), port=int(os.getenv("DB_PORT", 5432)),
                                 database=os.getenv("DB_NAME", "seafight_bot"),
                                 user=os.getenv("DB_USER", "postgres"), password=os.getenv("DB_PASSWORD"))
    try:
        users = await conn.fetch("SELECT user_id, username, first_name, created_at, updated_at FROM users")
        ratings = await conn.fetch("SELECT user_id, game_type, rating, games_won, games_lost, updated_at"
                                   " FROM player_ratings")
        scores = await conn.fetch("SELECT user_id, score, game_type, created_at FROM leaderboard")
    finally:
        await conn.close()
    return users, ratings, scores


def migrate(storage: Storage, users, ratings, scores) -> None:
    conn = storage.conn
    if conn.execute("SELECT 1 FROM ratings WHERE platform = ?", (PLATFORM,)).fetchone() or \
            conn.execute("SELECT 1 FROM scores WHERE platform = ? AND game LIKE 'sea_%'", (PLATFORM,)).fetchone():
        raise SystemExit("в SQLite уже есть рейтинг или рекорды морского боя TG — перенос, видимо, уже был")
    for u in users:
        name = format_player_name(u["username"], u["first_name"], u["user_id"])[:64]
        storage.upsert_user(PLATFORM, u["user_id"], name, u["user_id"], u["created_at"].timestamp())
    with conn:
        for r in ratings:
            conn.execute("INSERT INTO ratings (platform, user_id, game_type, rating, won, lost, updated_at)"
                         " VALUES (?, ?, ?, ?, ?, ?, ?)",
                         (PLATFORM, r["user_id"], r["game_type"], r["rating"], r["games_won"], r["games_lost"],
                          r["updated_at"].timestamp()))
        best = {}
        for s in scores:
            game = SOLO_GAMES.get(s["game_type"])
            if game is None:
                continue
            played = s["created_at"].timestamp()
            conn.execute("INSERT INTO scores (platform, user_id, game, score, level, played_at)"
                         " VALUES (?, ?, ?, ?, NULL, ?)", (PLATFORM, s["user_id"], game, s["score"], played))
            key = (s["user_id"], game)
            best[key] = max(best.get(key, (s["score"], played)), (s["score"], played))
    with conn:
        for (user_id, game), (score, played) in best.items():
            # уровней у морского боя нет — только лучший результат
            conn.execute(
                """INSERT INTO progress (platform, user_id, game, level, win_streak, fail_count,
                                         last_success_level, last_played_at, best_score)
                   VALUES (?, ?, ?, 1, 0, 0, 1, ?, ?)
                   ON CONFLICT (platform, user_id, game) DO UPDATE SET
                       best_score = MAX(progress.best_score, excluded.best_score)""",
                (PLATFORM, user_id, game, played, score))
    print(f"перенесено: игроков {len(users)}, строк рейтинга {len(ratings)}, рекордов {len(scores)}")


def main() -> None:
    users, ratings, scores = asyncio.run(fetch_all())
    Path(config.GAMES_DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    storage = Storage(config.GAMES_DB_PATH)
    try:
        migrate(storage, users, ratings, scores)
    finally:
        storage.close()


if __name__ == "__main__":
    main()

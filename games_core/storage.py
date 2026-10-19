"""Прогресс, рекорды и пользователи в SQLite.

Запросы крошечные (единицы в секунду), поэтому синхронный sqlite3 без пула.
Ключ пользователя — (platform, user_id), чтобы один файл мог обслуживать
несколько мессенджеров.
"""
import json
import sqlite3
from typing import Dict, List, Optional, Tuple

from .progression import Progress

SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    platform    TEXT NOT NULL,
    user_id     INTEGER NOT NULL,
    name        TEXT NOT NULL,
    chat_id     INTEGER,
    created_at  REAL NOT NULL,
    updated_at  REAL NOT NULL,
    PRIMARY KEY (platform, user_id)
);
CREATE TABLE IF NOT EXISTS progress (
    platform            TEXT NOT NULL,
    user_id             INTEGER NOT NULL,
    game                TEXT NOT NULL,
    level               INTEGER NOT NULL,
    win_streak          INTEGER NOT NULL,
    fail_count          INTEGER NOT NULL,
    last_success_level  INTEGER NOT NULL,
    last_played_at      REAL,
    best_score          INTEGER NOT NULL,
    PRIMARY KEY (platform, user_id, game)
);
CREATE TABLE IF NOT EXISTS scores (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    platform    TEXT NOT NULL,
    user_id     INTEGER NOT NULL,
    game        TEXT NOT NULL,
    score       INTEGER NOT NULL,
    level       INTEGER,
    played_at   REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS scores_game_score ON scores (platform, game, score DESC);
CREATE TABLE IF NOT EXISTS mp_games (
    platform    TEXT NOT NULL,
    code        TEXT NOT NULL,
    status      TEXT NOT NULL,
    state       TEXT NOT NULL,          -- MpGame.to_dict() в JSON
    updated_at  REAL NOT NULL,
    PRIMARY KEY (platform, code)
);
CREATE TABLE IF NOT EXISTS ratings (
    platform    TEXT NOT NULL,
    user_id     INTEGER NOT NULL,
    game_type   TEXT NOT NULL,          -- mp_full / mp_reduced
    rating      INTEGER NOT NULL,
    won         INTEGER NOT NULL,
    lost        INTEGER NOT NULL,
    updated_at  REAL NOT NULL,
    PRIMARY KEY (platform, user_id, game_type)
);
"""


class Storage:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        if path != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)

    def close(self) -> None:
        self.conn.close()

    def upsert_user(self, platform: str, user_id: int, name: str, chat_id: Optional[int], now: float) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO users (platform, user_id, name, chat_id, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?)
                   ON CONFLICT (platform, user_id) DO UPDATE SET
                       name = excluded.name,
                       chat_id = COALESCE(excluded.chat_id, users.chat_id),
                       updated_at = excluded.updated_at""",
                (platform, user_id, name, chat_id, now, now),
            )

    def load_progress(self, platform: str, user_id: int, game: str) -> Progress:
        row = self.conn.execute(
            "SELECT * FROM progress WHERE platform = ? AND user_id = ? AND game = ?",
            (platform, user_id, game),
        ).fetchone()
        if row is None:
            return Progress()
        return Progress(
            level=row["level"],
            win_streak=row["win_streak"],
            fail_count=row["fail_count"],
            last_success_level=row["last_success_level"],
            last_played_at=row["last_played_at"],
            best_score=row["best_score"],
        )

    def save_result(self, platform: str, user_id: int, game: str, p: Progress,
                    score: Optional[int], now: float) -> bool:
        """Сохранить прогресс и, если score не None, результат партии.

        Возвращает True, если это новый личный рекорд.
        """
        is_record = score is not None and score > p.best_score
        if is_record:
            p.best_score = score
        p.last_played_at = now
        with self.conn:
            self.conn.execute(
                """INSERT INTO progress (platform, user_id, game, level, win_streak, fail_count,
                                         last_success_level, last_played_at, best_score)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (platform, user_id, game) DO UPDATE SET
                       level = excluded.level,
                       win_streak = excluded.win_streak,
                       fail_count = excluded.fail_count,
                       last_success_level = excluded.last_success_level,
                       last_played_at = excluded.last_played_at,
                       best_score = excluded.best_score""",
                (platform, user_id, game, p.level, p.win_streak, p.fail_count,
                 p.last_success_level, p.last_played_at, p.best_score),
            )
            if score is not None:
                self.conn.execute(
                    "INSERT INTO scores (platform, user_id, game, score, level, played_at)"
                    " VALUES (?, ?, ?, ?, ?, ?)",
                    (platform, user_id, game, score, p.level, now),
                )
        return is_record

    def reset_user(self, platform: str, user_id: int) -> None:
        """Стереть уровни и результаты игрока (для отладки)."""
        with self.conn:
            for table in ("progress", "scores", "ratings"):
                self.conn.execute(f"DELETE FROM {table} WHERE platform = ? AND user_id = ?",
                                  (platform, user_id))

    def top(self, platform: str, game: str, limit: int = 10) -> List[Tuple[int, str, int]]:
        """Лучший результат каждого игрока: [(user_id, name, score)]."""
        rows = self.conn.execute(
            """SELECT s.user_id, COALESCE(u.name, '?') AS name, MAX(s.score) AS best
               FROM scores s
               LEFT JOIN users u ON u.platform = s.platform AND u.user_id = s.user_id
               WHERE s.platform = ? AND s.game = ?
               GROUP BY s.user_id
               ORDER BY best DESC, MIN(s.played_at)
               LIMIT ?""",
            (platform, game, limit),
        ).fetchall()
        return [(r["user_id"], r["name"], r["best"]) for r in rows]

    # --- морской бой с другом ---

    def save_mp(self, platform: str, code: str, status: str, state: dict, now: float) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO mp_games (platform, code, status, state, updated_at) VALUES (?, ?, ?, ?, ?)
                   ON CONFLICT (platform, code) DO UPDATE SET
                       status = excluded.status, state = excluded.state, updated_at = excluded.updated_at""",
                (platform, code, status, json.dumps(state, ensure_ascii=False), now),
            )

    def load_mp(self, platform: str, statuses: Tuple[str, ...]) -> List[dict]:
        """Партии с этими статусами (незаконченные — при старте бота)."""
        marks = ",".join("?" * len(statuses))
        rows = self.conn.execute(
            f"SELECT state FROM mp_games WHERE platform = ? AND status IN ({marks})",
            (platform, *statuses),
        ).fetchall()
        return [json.loads(r["state"]) for r in rows]

    def mp_code_used(self, platform: str, code: str) -> bool:
        return self.conn.execute("SELECT 1 FROM mp_games WHERE platform = ? AND code = ?",
                                 (platform, code)).fetchone() is not None

    def rating(self, platform: str, user_id: int, game_type: str, default: int) -> int:
        row = self.conn.execute(
            "SELECT rating FROM ratings WHERE platform = ? AND user_id = ? AND game_type = ?",
            (platform, user_id, game_type),
        ).fetchone()
        return row["rating"] if row else default

    def save_match(self, platform: str, game_type: str, winner: int, loser: int,
                   ratings: Dict[int, int], now: float) -> None:
        """Новые рейтинги обоих и счётчики побед/поражений — одной транзакцией."""
        with self.conn:
            for uid, won in ((winner, 1), (loser, 0)):
                self.conn.execute(
                    """INSERT INTO ratings (platform, user_id, game_type, rating, won, lost, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT (platform, user_id, game_type) DO UPDATE SET
                           rating = excluded.rating, won = ratings.won + excluded.won,
                           lost = ratings.lost + excluded.lost, updated_at = excluded.updated_at""",
                    (platform, uid, game_type, ratings[uid], won, 1 - won, now),
                )

    def top_ratings(self, platform: str, game_type: str, limit: int = 10) -> List[Tuple[int, str, int, int, int]]:
        """[(user_id, name, rating, won, lost)] по убыванию рейтинга."""
        rows = self.conn.execute(
            """SELECT r.user_id, COALESCE(u.name, '?') AS name, r.rating, r.won, r.lost
               FROM ratings r
               LEFT JOIN users u ON u.platform = r.platform AND u.user_id = r.user_id
               WHERE r.platform = ? AND r.game_type = ?
               ORDER BY r.rating DESC, r.updated_at
               LIMIT ?""",
            (platform, game_type, limit),
        ).fetchall()
        return [(r["user_id"], r["name"], r["rating"], r["won"], r["lost"]) for r in rows]

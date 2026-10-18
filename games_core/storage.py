"""Прогресс, рекорды и пользователи в SQLite.

Запросы крошечные (единицы в секунду), поэтому синхронный sqlite3 без пула.
Ключ пользователя — (platform, user_id), чтобы один файл мог обслуживать
несколько мессенджеров.
"""
import sqlite3
from typing import List, Optional, Tuple

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
            for table in ("progress", "scores"):
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

"""Прогресс, рекорды и пользователи в SQLite.

Запросы крошечные (единицы в секунду), поэтому синхронный sqlite3 без пула.
Ключ пользователя — (platform, user_id), чтобы один файл мог обслуживать
несколько мессенджеров.
"""
import json
import sqlite3
from typing import Callable, Dict, List, Optional, Tuple

from .motivation import Partia
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
CREATE TABLE IF NOT EXISTS friend_codes (
    platform    TEXT NOT NULL,
    user_id     INTEGER NOT NULL,
    code        TEXT NOT NULL,          -- постоянная ссылка-приглашение ?start=fr_<code>
    PRIMARY KEY (platform, code),
    UNIQUE (platform, user_id)
);
CREATE TABLE IF NOT EXISTS friends (
    platform    TEXT NOT NULL,
    user_id     INTEGER NOT NULL,
    friend_id   INTEGER NOT NULL,       -- дружба записана в обе стороны
    created_at  REAL NOT NULL,
    PRIMARY KEY (platform, user_id, friend_id)
);
CREATE TABLE IF NOT EXISTS settings (
    platform            TEXT NOT NULL,
    user_id             INTEGER NOT NULL,
    friend_notify       INTEGER NOT NULL DEFAULT 1,
    reminder_hour       INTEGER,        -- NULL — напоминание выключено
    friend_notified_day TEXT,           -- день (по Москве) последнего уведомления от друзей
    reminded_day        TEXT,           -- день последнего напоминания
    weekly_report       INTEGER NOT NULL DEFAULT 1,   -- итоги недели по воскресеньям
    reported_week       TEXT,           -- понедельник недели последнего отчёта
    hero                TEXT,           -- герой на картинке пути; NULL — по умолчанию
    PRIMARY KEY (platform, user_id)
);
CREATE TABLE IF NOT EXISTS hero_purchases (
    platform    TEXT NOT NULL,
    user_id     INTEGER NOT NULL,
    hero        TEXT NOT NULL,
    price       INTEGER NOT NULL,     -- монет потрачено
    bought_at   REAL NOT NULL,
    PRIMARY KEY (platform, user_id, hero)
);
CREATE INDEX IF NOT EXISTS scores_user_time ON scores (platform, user_id, played_at);
CREATE TABLE IF NOT EXISTS ai_results (
    platform    TEXT NOT NULL,
    user_id     INTEGER NOT NULL,
    level       TEXT NOT NULL,          -- normal / advanced
    ship_set    TEXT NOT NULL,          -- full / reduced
    won         INTEGER NOT NULL,
    lost        INTEGER NOT NULL,
    updated_at  REAL NOT NULL,
    PRIMARY KEY (platform, user_id, level, ship_set)
);
CREATE TABLE IF NOT EXISTS boats_results (
    score_id    INTEGER PRIMARY KEY,    -- scores.id этой партии (там же очки и уровень партии)
    platform    TEXT NOT NULL,
    user_id     INTEGER NOT NULL,
    level       INTEGER NOT NULL,       -- уровень партии
    correct     INTEGER NOT NULL,       -- верных прибытий
    arrived     INTEGER NOT NULL,       -- всего прибытий
    opened      INTEGER NOT NULL        -- самый высокий открытый уровень после партии
);
CREATE INDEX IF NOT EXISTS boats_results_user ON boats_results (platform, user_id, level);
"""

SETTING_FIELDS = ("friend_notify", "reminder_hour", "friend_notified_day", "reminded_day",
                  "weekly_report", "reported_week", "hero")
# колонки, добавленные после первого выката: в старой БД их досоздаёт __init__
MIGRATIONS = (
    ("settings", "weekly_report", "INTEGER NOT NULL DEFAULT 1"),
    ("settings", "reported_week", "TEXT"),
    ("settings", "hero", "TEXT"),
)


class Storage:
    def __init__(self, path: str):
        self.conn = sqlite3.connect(path)
        self.conn.row_factory = sqlite3.Row
        if path != ":memory:":
            self.conn.execute("PRAGMA journal_mode=WAL")
        self.conn.executescript(SCHEMA)
        for table, column, decl in MIGRATIONS:
            have = {r["name"] for r in self.conn.execute(f"PRAGMA table_info({table})")}
            if column not in have:
                with self.conn:
                    self.conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")

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

    def save_boats(self, platform: str, user_id: int, p: Progress, score: int, level: int,
                   correct: int, arrived: int, now: float) -> bool:
        """«Кораблики»: прогресс (p.level — самый высокий открытый уровень), партия в scores с уровнем
        партии и её «верно из прибывших» в boats_results. True — новый личный рекорд."""
        is_record = score > p.best_score
        if is_record:
            p.best_score = score
        p.last_played_at = now
        with self.conn:
            self.conn.execute(
                """INSERT INTO progress (platform, user_id, game, level, win_streak, fail_count,
                                         last_success_level, last_played_at, best_score)
                   VALUES (?, ?, 'boats', ?, 0, 0, ?, ?, ?)
                   ON CONFLICT (platform, user_id, game) DO UPDATE SET
                       level = excluded.level, last_success_level = excluded.last_success_level,
                       last_played_at = excluded.last_played_at, best_score = excluded.best_score""",
                (platform, user_id, p.level, p.level, now, p.best_score))
            cur = self.conn.execute(
                "INSERT INTO scores (platform, user_id, game, score, level, played_at) VALUES (?, ?, 'boats', ?, ?, ?)",
                (platform, user_id, score, level, now))
            self.conn.execute(
                "INSERT INTO boats_results (score_id, platform, user_id, level, correct, arrived, opened)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (cur.lastrowid, platform, user_id, level, correct, arrived, p.level))
        return is_record

    def boats_best(self, platform: str, user_id: int) -> Dict[int, Tuple[int, int]]:
        """Лучшая партия «Корабликов» на каждом уровне: {уровень: (верно, прибыло)} —
        больше верных, при равенстве — выше точность."""
        rows = self.conn.execute(
            "SELECT level, correct, arrived FROM boats_results WHERE platform = ? AND user_id = ?",
            (platform, user_id)).fetchall()
        best: Dict[int, Tuple[int, int]] = {}
        for r in rows:
            cur = best.get(r["level"])
            key = (r["correct"], r["correct"] / r["arrived"] if r["arrived"] else 0.0)
            if cur is None or key > (cur[0], cur[0] / cur[1] if cur[1] else 0.0):
                best[r["level"]] = (r["correct"], r["arrived"])
        return best

    def partias(self, platform: str, user_id: int) -> List[Partia]:
        """История партий игрока по времени — из неё считаются путь и серия.
        У «Корабликов» уровень в истории — самый высокий открытый после партии (по нему путь и значки)."""
        rows = self.conn.execute(
            """SELECT s.game, COALESCE(b.opened, s.level) AS level, s.played_at FROM scores s
               LEFT JOIN boats_results b ON b.score_id = s.id
               WHERE s.platform = ? AND s.user_id = ? ORDER BY s.played_at, s.id""",
            (platform, user_id)).fetchall()
        return [Partia(r["game"], r["level"], r["played_at"]) for r in rows]

    def add_score(self, platform: str, user_id: int, game: str, score: int, level: Optional[int],
                  at: float) -> None:
        """Партия в истории без изменения уровня и рекорда: бой с компьютером, отладка задним числом."""
        with self.conn:
            self.conn.execute(
                "INSERT INTO scores (platform, user_id, game, score, level, played_at) VALUES (?, ?, ?, ?, ?, ?)",
                (platform, user_id, game, score, level, at))

    def reset_user(self, platform: str, user_id: int) -> None:
        """Стереть уровни и результаты игрока (для отладки)."""
        with self.conn:
            for table in ("progress", "scores", "ratings", "hero_purchases", "ai_results", "boats_results"):
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

    # --- бой с компьютером ---

    def save_ai_result(self, platform: str, user_id: int, level: str, ship_set: str, won: bool,
                       now: float) -> None:
        with self.conn:
            self.conn.execute(
                """INSERT INTO ai_results (platform, user_id, level, ship_set, won, lost, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (platform, user_id, level, ship_set) DO UPDATE SET
                       won = ai_results.won + excluded.won, lost = ai_results.lost + excluded.lost,
                       updated_at = excluded.updated_at""",
                (platform, user_id, level, ship_set, int(won), int(not won), now))

    def top_ai(self, platform: str, level: str, limit: int = 10) -> List[Tuple[int, str, int, int]]:
        """[(user_id, name, побед, поражений)] на этом уровне (оба набора), по числу побед."""
        rows = self.conn.execute(
            """SELECT a.user_id, COALESCE(u.name, '?') AS name, SUM(a.won) AS won, SUM(a.lost) AS lost,
                      MIN(a.updated_at) AS first
               FROM ai_results a
               LEFT JOIN users u ON u.platform = a.platform AND u.user_id = a.user_id
               WHERE a.platform = ? AND a.level = ?
               GROUP BY a.user_id
               ORDER BY won DESC, lost, first
               LIMIT ?""",
            (platform, level, limit)).fetchall()
        return [(r["user_id"], r["name"], r["won"], r["lost"]) for r in rows]

    def ai_results_of(self, platform: str, user_id: int) -> Dict[str, Tuple[int, int]]:
        """{уровень: (побед, поражений)} по обоим наборам."""
        rows = self.conn.execute(
            """SELECT level, SUM(won) AS won, SUM(lost) AS lost FROM ai_results
               WHERE platform = ? AND user_id = ? GROUP BY level""",
            (platform, user_id)).fetchall()
        return {r["level"]: (r["won"], r["lost"]) for r in rows}

    # --- игроки ---

    def user(self, platform: str, user_id: int) -> Optional[sqlite3.Row]:
        return self.conn.execute("SELECT * FROM users WHERE platform = ? AND user_id = ?",
                                 (platform, user_id)).fetchone()

    def names(self, platform: str, user_ids: List[int]) -> Dict[int, str]:
        if not user_ids:
            return {}
        marks = ",".join("?" * len(user_ids))
        rows = self.conn.execute(f"SELECT user_id, name FROM users WHERE platform = ? AND user_id IN ({marks})",
                                 (platform, *user_ids)).fetchall()
        return {r["user_id"]: r["name"] for r in rows}

    def records(self, platform: str, user_id: int) -> List[Tuple[str, int, int]]:
        """[(game, best_score, level)] — где есть рекорд."""
        rows = self.conn.execute(
            "SELECT game, best_score, level FROM progress WHERE platform = ? AND user_id = ? AND best_score > 0",
            (platform, user_id)).fetchall()
        return [(r["game"], r["best_score"], r["level"]) for r in rows]

    def ratings_of(self, platform: str, user_id: int) -> List[Tuple[str, int, int, int]]:
        """[(game_type, rating, won, lost)]"""
        rows = self.conn.execute(
            "SELECT game_type, rating, won, lost FROM ratings WHERE platform = ? AND user_id = ?",
            (platform, user_id)).fetchall()
        return [(r["game_type"], r["rating"], r["won"], r["lost"]) for r in rows]

    def played_since(self, platform: str, user_ids: List[int], since: float) -> Dict[int, Dict[str, Tuple[int, int]]]:
        """Партии с момента since: {user_id: {game: (партий, лучший счёт)}}."""
        if not user_ids:
            return {}
        marks = ",".join("?" * len(user_ids))
        rows = self.conn.execute(
            f"""SELECT user_id, game, COUNT(*) AS n, MAX(score) AS best FROM scores
                WHERE platform = ? AND played_at >= ? AND user_id IN ({marks})
                GROUP BY user_id, game""",
            (platform, since, *user_ids)).fetchall()
        out: Dict[int, Dict[str, Tuple[int, int]]] = {}
        for r in rows:
            out.setdefault(r["user_id"], {})[r["game"]] = (r["n"], r["best"])
        return out

    # --- друзья ---

    def friend_code(self, platform: str, user_id: int, make_code: Callable[[], str]) -> str:
        """Постоянный код ссылки-приглашения игрока; при первом запросе — новый."""
        row = self.conn.execute("SELECT code FROM friend_codes WHERE platform = ? AND user_id = ?",
                                (platform, user_id)).fetchone()
        if row is not None:
            return row["code"]
        while True:
            code = make_code()
            try:
                with self.conn:
                    self.conn.execute("INSERT INTO friend_codes (platform, user_id, code) VALUES (?, ?, ?)",
                                      (platform, user_id, code))
                return code
            except sqlite3.IntegrityError:
                continue    # такой код уже у кого-то есть

    def code_owner(self, platform: str, code: str) -> Optional[int]:
        row = self.conn.execute("SELECT user_id FROM friend_codes WHERE platform = ? AND code = ?",
                                (platform, code)).fetchone()
        return row["user_id"] if row else None

    def add_friends(self, platform: str, a: int, b: int, now: float) -> bool:
        """Подружить a и b. False — уже были друзьями."""
        if self.are_friends(platform, a, b):
            return False
        with self.conn:
            for x, y in ((a, b), (b, a)):
                self.conn.execute(
                    "INSERT OR IGNORE INTO friends (platform, user_id, friend_id, created_at) VALUES (?, ?, ?, ?)",
                    (platform, x, y, now))
        return True

    def are_friends(self, platform: str, a: int, b: int) -> bool:
        return self.conn.execute("SELECT 1 FROM friends WHERE platform = ? AND user_id = ? AND friend_id = ?",
                                 (platform, a, b)).fetchone() is not None

    def friends(self, platform: str, user_id: int) -> List[int]:
        rows = self.conn.execute("SELECT friend_id FROM friends WHERE platform = ? AND user_id = ?",
                                 (platform, user_id)).fetchall()
        return [r["friend_id"] for r in rows]

    # --- настройки и уведомления ---

    def settings(self, platform: str, user_id: int) -> Dict[str, object]:
        row = self.conn.execute("SELECT * FROM settings WHERE platform = ? AND user_id = ?",
                                (platform, user_id)).fetchone()
        if row is None:
            return {"friend_notify": 1, "reminder_hour": None, "friend_notified_day": None, "reminded_day": None,
                    "weekly_report": 1, "reported_week": None, "hero": None}
        return {k: row[k] for k in SETTING_FIELDS}

    def update_settings(self, platform: str, user_id: int, **fields) -> None:
        unknown = set(fields) - set(SETTING_FIELDS)
        if unknown:
            raise ValueError(unknown)
        current = self.settings(platform, user_id)
        current.update(fields)
        with self.conn:
            self.conn.execute(
                """INSERT INTO settings (platform, user_id, friend_notify, reminder_hour,
                                         friend_notified_day, reminded_day, weekly_report, reported_week, hero)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT (platform, user_id) DO UPDATE SET
                       friend_notify = excluded.friend_notify, reminder_hour = excluded.reminder_hour,
                       friend_notified_day = excluded.friend_notified_day, reminded_day = excluded.reminded_day,
                       weekly_report = excluded.weekly_report, reported_week = excluded.reported_week,
                       hero = excluded.hero""",
                (platform, user_id, *(current[k] for k in SETTING_FIELDS)))

    # --- герои ---

    def hero_purchases(self, platform: str, user_id: int) -> Dict[str, int]:
        """Купленные герои: {герой: цена}."""
        rows = self.conn.execute("SELECT hero, price FROM hero_purchases WHERE platform = ? AND user_id = ?",
                                 (platform, user_id)).fetchall()
        return {r["hero"]: r["price"] for r in rows}

    def buy_hero(self, platform: str, user_id: int, hero: str, price: int, at: float) -> None:
        with self.conn:
            self.conn.execute(
                "INSERT OR IGNORE INTO hero_purchases (platform, user_id, hero, price, bought_at) VALUES (?, ?, ?, ?, ?)",
                (platform, user_id, hero, price, at))

    def friend_notify_due(self, platform: str, since: float, today: str) -> Dict[int, List[int]]:
        """Кому пора уведомление от друзей: {user_id: [друзья в порядке первой партии с since]}.

        Уведомления включены, сегодня ещё не приходили, сам с since не играл, а кто-то из друзей — играл.
        """
        rows = self.conn.execute(
            """SELECT f.user_id, f.friend_id, MIN(s.played_at) AS first FROM friends f
               JOIN scores s ON s.platform = f.platform AND s.user_id = f.friend_id AND s.played_at >= :since
               LEFT JOIN settings st ON st.platform = f.platform AND st.user_id = f.user_id
               WHERE f.platform = :platform AND COALESCE(st.friend_notify, 1) = 1
                 AND COALESCE(st.friend_notified_day, '') != :today
                 AND NOT EXISTS (SELECT 1 FROM scores m WHERE m.platform = f.platform
                                 AND m.user_id = f.user_id AND m.played_at >= :since)
               GROUP BY f.user_id, f.friend_id
               ORDER BY f.user_id, first""",
            {"platform": platform, "since": since, "today": today}).fetchall()
        out: Dict[int, List[int]] = {}
        for r in rows:
            out.setdefault(r["user_id"], []).append(r["friend_id"])
        return out

    def weekly_due(self, platform: str, since: float, week: str) -> List[int]:
        """Кому пора итоги недели: играл с понедельника (since), отчёт включён и за эту неделю не приходил."""
        rows = self.conn.execute(
            """SELECT DISTINCT s.user_id FROM scores s
               LEFT JOIN settings st ON st.platform = s.platform AND st.user_id = s.user_id
               WHERE s.platform = :platform AND s.played_at >= :since
                 AND COALESCE(st.weekly_report, 1) = 1 AND COALESCE(st.reported_week, '') != :week
               ORDER BY s.user_id""",
            {"platform": platform, "since": since, "week": week}).fetchall()
        return [r["user_id"] for r in rows]

    def reminders_due(self, platform: str, hour: int, since: float, today: str) -> List[int]:
        """Кому пора напоминание: час наступил (с запасом в 2 часа), сегодня не было, сам не играл."""
        rows = self.conn.execute(
            """SELECT st.user_id FROM settings st
               WHERE st.platform = :platform AND st.reminder_hour IS NOT NULL
                 AND st.reminder_hour <= :hour AND :hour < st.reminder_hour + 2
                 AND COALESCE(st.reminded_day, '') != :today
                 AND NOT EXISTS (SELECT 1 FROM scores m WHERE m.platform = st.platform
                                 AND m.user_id = st.user_id AND m.played_at >= :since)""",
            {"platform": platform, "hour": hour, "since": since, "today": today}).fetchall()
        return [r["user_id"] for r in rows]

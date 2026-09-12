import asyncpg
from typing import Optional, List
from datetime import datetime

from config import DB_CONFIG
from .models import User, LeaderboardEntry
from .multiplayer_models import MultiplayerGame, MultiplayerStats


class Database:
    def __init__(self):
        self.pool = None

    async def connect(self):
        """Подключение к PostgreSQL"""
        self.pool = await asyncpg.create_pool(**DB_CONFIG)

    async def close(self):
        """Закрытие соединения с PostgreSQL"""
        if self.pool:
            await self.pool.close()

    async def init_tables(self):
        """Создание таблиц и миграции"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    user_id BIGINT PRIMARY KEY,
                    first_name VARCHAR(255) NOT NULL,
                    last_name VARCHAR(255),
                    username VARCHAR(255),
                    phone_number VARCHAR(20),
                    is_bot BOOLEAN DEFAULT FALSE,
                    language_code VARCHAR(10) DEFAULT 'en',
                    is_premium BOOLEAN DEFAULT FALSE,
                    source VARCHAR(255),
                    leaderboard_name VARCHAR(255),
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS leaderboard (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL,
                    name VARCHAR(255) NOT NULL,
                    score INTEGER NOT NULL,
                    game_type VARCHAR(20) DEFAULT 'solo_full',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE
                )
            ''')

            # Миграция: добавляем колонку game_type если её нет
            await conn.execute('''
                DO $$
                BEGIN
                    IF NOT EXISTS (
                        SELECT 1 FROM information_schema.columns
                        WHERE table_name = 'leaderboard' AND column_name = 'game_type'
                    ) THEN
                        ALTER TABLE leaderboard ADD COLUMN game_type VARCHAR(20) DEFAULT 'solo_full';
                    END IF;
                END $$
            ''')

            # Индексы для быстрого поиска
            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_leaderboard_score 
                ON leaderboard(score DESC)
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_leaderboard_user_id 
                ON leaderboard(user_id)
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_leaderboard_game_type
                ON leaderboard(game_type)
            ''')

            # Таблицы мультиплеера
            await conn.execute('''
                CREATE TABLE IF NOT EXISTS multiplayer_games (
                    game_id SERIAL PRIMARY KEY,
                    player1_id BIGINT NOT NULL REFERENCES users(user_id),
                    player2_id BIGINT REFERENCES users(user_id),
                    status VARCHAR(20) DEFAULT 'waiting',
                    placement_mode VARCHAR(10) DEFAULT 'auto',
                    ship_set VARCHAR(10) DEFAULT 'full',
                    join_code VARCHAR(10),
                    placement_complete1 BOOLEAN DEFAULT FALSE,
                    placement_complete2 BOOLEAN DEFAULT FALSE,
                    current_turn BIGINT DEFAULT 0,
                    turn_start_time TIMESTAMP,
                    time_limit_seconds INTEGER,
                    board1 JSONB DEFAULT '[]',
                    board2 JSONB DEFAULT '[]',
                    attacks1 JSONB DEFAULT '[]',
                    attacks2 JSONB DEFAULT '[]',
                    score1 INTEGER DEFAULT 0,
                    score2 INTEGER DEFAULT 0,
                    winner_id BIGINT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    finished_at TIMESTAMP,
                    last_move_time TIMESTAMP,
                    timeouts_count1 INTEGER DEFAULT 0,
                    timeouts_count2 INTEGER DEFAULT 0
                )
            ''')

            # Миграции для старых установок: недостающие колонки
            await conn.execute('''
                ALTER TABLE multiplayer_games
                ADD COLUMN IF NOT EXISTS ship_set VARCHAR(10) DEFAULT 'full'
            ''')
            await conn.execute('''
                ALTER TABLE multiplayer_games
                ADD COLUMN IF NOT EXISTS join_code VARCHAR(10)
            ''')
            await conn.execute('''
                CREATE UNIQUE INDEX IF NOT EXISTS idx_mp_games_join_code_unique
                ON multiplayer_games(join_code) WHERE join_code IS NOT NULL
            ''')

            await conn.execute('''
                CREATE TABLE IF NOT EXISTS multiplayer_stats (
                    id SERIAL PRIMARY KEY,
                    user_id BIGINT NOT NULL REFERENCES users(user_id),
                    opponent_id BIGINT NOT NULL REFERENCES users(user_id),
                    games_played INTEGER DEFAULT 0,
                    games_won INTEGER DEFAULT 0,
                    games_lost INTEGER DEFAULT 0,
                    last_played_at TIMESTAMP,
                    UNIQUE(user_id, opponent_id)
                )
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_mp_games_player1
                ON multiplayer_games(player1_id)
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_mp_games_player2
                ON multiplayer_games(player2_id)
            ''')

            await conn.execute('''
                CREATE INDEX IF NOT EXISTS idx_mp_games_status
                ON multiplayer_games(status)
            ''')

    async def get_user(self, user_id: int) -> Optional[User]:
        """Получить информацию о пользователе"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                'SELECT * FROM users WHERE user_id = $1',
                user_id
            )
            if row:
                return User(**dict(row))
            return None

    async def save_user(self, user: User):
        """Сохранить или обновить информацию о пользователе"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO users (
                    user_id, first_name, last_name, username, phone_number,
                    is_bot, language_code, is_premium, source, leaderboard_name
                )
                VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
                ON CONFLICT (user_id) DO UPDATE SET
                    first_name = EXCLUDED.first_name,
                    last_name = EXCLUDED.last_name,
                    username = EXCLUDED.username,
                    phone_number = EXCLUDED.phone_number,
                    is_bot = EXCLUDED.is_bot,
                    language_code = EXCLUDED.language_code,
                    is_premium = EXCLUDED.is_premium,
                    source = EXCLUDED.source,
                    leaderboard_name = COALESCE(EXCLUDED.leaderboard_name, users.leaderboard_name),
                    updated_at = CURRENT_TIMESTAMP
            ''', user.user_id, user.first_name, user.last_name, user.username,
                user.phone_number, user.is_bot, user.language_code,
                user.is_premium, user.source, user.leaderboard_name)

    async def update_leaderboard_name(self, user_id: int, leaderboard_name: str) -> bool:
        """Обновить имя для лидерборда"""
        if not self.is_safe_leaderboard_name(leaderboard_name):
            return False

        async with self.pool.acquire() as conn:
            await conn.execute(
                'UPDATE users SET leaderboard_name = $1 WHERE user_id = $2',
                leaderboard_name, user_id
            )
        return True

    async def add_leaderboard_entry(self, user_id: int, name: str, score: int,
                                     game_type: str = 'solo_full') -> int:
        """Добавить запись в лидерборд и вернуть позицию.
        game_type: 'solo_full', 'solo_reduced', 'mp_full'
        """
        async with self.pool.acquire() as conn:
            # Добавляем запись
            await conn.execute(
                'INSERT INTO leaderboard (user_id, name, score, game_type) VALUES ($1, $2, $3, $4)',
                user_id, name, score, game_type
            )

            # Получаем позицию в рамках данного типа
            result = await conn.fetchval('''
                SELECT COUNT(*) + 1 AS position
                FROM leaderboard
                WHERE game_type = $1 AND score > $2
            ''', game_type, score)
            return result

    async def get_top_leaderboard(self, limit: int = 100,
                                   game_type: str = None) -> List[dict]:
        """Получить топ лидерборда, опционально по типу игры"""
        async with self.pool.acquire() as conn:
            if game_type:
                rows = await conn.fetch('''
                    SELECT user_id, name, score, game_type, created_at
                    FROM leaderboard
                    WHERE game_type = $1
                    ORDER BY score DESC
                    LIMIT $2
                ''', game_type, limit)
            else:
                rows = await conn.fetch('''
                    SELECT user_id, name, score, game_type, created_at
                    FROM leaderboard
                    ORDER BY score DESC
                    LIMIT $1
                ''', limit)
            return [dict(row) for row in rows]

    @staticmethod
    def is_safe_leaderboard_name(name: str) -> bool:
        """Проверить безопасность имени для лидерборда"""
        import re
        if not name:
            return False
        pattern = r'^[a-zA-Zа-яА-Я0-9_ .-]+$'
        return re.match(pattern, name) is not None

    # ========== Мультиплеер ==========

    async def create_multiplayer_game(self, player1_id: int, placement_mode: str,
                                       time_limit: Optional[int],
                                       ship_set: str = 'full') -> int:
        """Создать игру мультиплеера"""
        import json
        import random
        import string
        from config import ROWS, COLS, EMPTY, SHIP, SHIPS, SHIPS_REDUCED
        from utils.game_logic import GameLogic

        ships = SHIPS if ship_set == 'full' else SHIPS_REDUCED
        game_logic = GameLogic(ROWS, COLS, EMPTY, SHIP)
        game_logic.generate_board(ships)

        board_json = json.dumps(game_logic.board.board)

        # Генерируем уникальный код для подключения
        join_code = await self._generate_join_code()

        async with self.pool.acquire() as conn:
            game_id = await conn.fetchval('''
                INSERT INTO multiplayer_games (
                    player1_id, status, join_code, placement_mode, ship_set, time_limit_seconds,
                    current_turn, board1, board2, attacks1, attacks2
                ) VALUES (
                    $1, $2, $3, $4, $5, $6, $7, $8, $9, $10, $11
                ) RETURNING game_id
            ''', player1_id, 'waiting', join_code, placement_mode, ship_set, time_limit, player1_id,
                board_json, board_json, '[]', '[]')

        return game_id

    async def _generate_join_code(self, length: int = 6) -> str:
        """Сгенерировать уникальный код для подключения (заглавные буквы + цифры)"""
        import random
        import string
        chars = string.ascii_uppercase + string.digits
        async with self.pool.acquire() as conn:
            while True:
                code = ''.join(random.choices(chars, k=length))
                exists = await conn.fetchval(
                    'SELECT 1 FROM multiplayer_games WHERE join_code = $1', code
                )
                if not exists:
                    return code

    async def get_multiplayer_game(self, game_id: int) -> Optional[dict]:
        """Получить игру мультиплеера по game_id"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT * FROM multiplayer_games WHERE game_id = $1
            ''', game_id)

        return dict(row) if row else None

    async def get_game_by_join_code(self, join_code: str) -> Optional[dict]:
        """Получить игру мультиплеера по коду подключения"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT * FROM multiplayer_games WHERE join_code = $1
            ''', join_code)

        return dict(row) if row else None

    async def join_multiplayer_game(self, game_id: int, player2_id: int) -> bool:
        """Подключиться к игре мультиплеера"""
        async with self.pool.acquire() as conn:
            result = await conn.execute('''
                UPDATE multiplayer_games
                SET player2_id = $1, status = 'placing'
                WHERE game_id = $2 AND player2_id IS NULL
            ''', player2_id, game_id)

        return result == 'UPDATE 1'

    async def update_multiplayer_game(self, game: MultiplayerGame) -> bool:
        """Обновить игру мультиплеера"""
        async with self.pool.acquire() as conn:
            result = await conn.execute('''
                UPDATE multiplayer_games
                SET status = $1,
                    placement_complete1 = $2,
                    placement_complete2 = $3,
                    current_turn = $4,
                    turn_start_time = $5,
                    board1 = $6,
                    board2 = $7,
                    attacks1 = $8,
                    attacks2 = $9,
                    score1 = $10,
                    score2 = $11,
                    winner_id = $12,
                    finished_at = $13,
                    last_move_time = $14,
                    timeouts_count1 = $15,
                    timeouts_count2 = $16,
                    join_code = $17
                WHERE game_id = $18
            ''', game.status, game.placement_complete1, game.placement_complete2,
                game.current_turn, game.turn_start_time, game.board1, game.board2,
                game.attacks1, game.attacks2, game.score1, game.score2,
                game.winner_id, game.finished_at, game.last_move_time,
                game.timeouts_count1, game.timeouts_count2,
                game.join_code, game.game_id)

        return result == 'UPDATE 1'

    async def update_board(self, game_id: int, player_num: int, board_json: str) -> bool:
        """Точечно обновить доску одного игрока (не затирая остальные поля)"""
        if player_num not in (1, 2):
            return False
        async with self.pool.acquire() as conn:
            result = await conn.execute(f'''
                UPDATE multiplayer_games
                SET board{player_num} = $1
                WHERE game_id = $2
            ''', board_json, game_id)

        return result == 'UPDATE 1'

    async def try_activate_game(self, game_id: int, first_turn: int) -> bool:
        """Атомарно перевести игру в статус active.
        Возвращает False, если игра уже активирована (защита от двойного старта)."""
        async with self.pool.acquire() as conn:
            result = await conn.execute('''
                UPDATE multiplayer_games
                SET status = 'active', current_turn = $2, turn_start_time = CURRENT_TIMESTAMP
                WHERE game_id = $1 AND status IN ('waiting', 'placing')
            ''', game_id, first_turn)

        return result == 'UPDATE 1'

    async def set_placement_complete(self, game_id: int, player_num: int) -> bool:
        """Пометить расстановку как завершённую"""
        if player_num not in (1, 2):
            return False
        async with self.pool.acquire() as conn:
            column = f'placement_complete{player_num}'
            result = await conn.execute(f'''
                UPDATE multiplayer_games
                SET {column} = TRUE
                WHERE game_id = $1
            ''', game_id)

        return result == 'UPDATE 1'

    async def make_move(self, game_id: int, player_num: int, x: int, y: int, result: str) -> bool:
        """Сделать ход"""
        import json

        async with self.pool.acquire() as conn:
            # Получаем текущие атаки
            attacks_column = f'attacks{player_num}'
            row = await conn.fetchrow(f'SELECT {attacks_column} FROM multiplayer_games WHERE game_id = $1', game_id)
            attacks = json.loads(row[attacks_column]) if row[attacks_column] else []

            # Добавляем новый ход
            attacks.append({'x': x, 'y': y, 'result': result})
            attacks_json = json.dumps(attacks)

            # Обновляем
            attacks_update_column = f'attacks{player_num}'
            result = await conn.execute(f'''
                UPDATE multiplayer_games
                SET {attacks_update_column} = $1, last_move_time = CURRENT_TIMESTAMP
                WHERE game_id = $2
            ''', attacks_json, game_id)

        return result == 'UPDATE 1'

    async def get_all_active_games(self) -> List[dict]:
        """Все игры в статусе active (восстановление таймеров после рестарта)"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT * FROM multiplayer_games WHERE status = 'active'
            ''')

        return [dict(row) for row in rows]

    async def get_active_game_for_user(self, user_id: int) -> Optional[dict]:
        """Получить активную игру пользователя"""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow('''
                SELECT * FROM multiplayer_games
                WHERE (player1_id = $1 OR player2_id = $1)
                AND status IN ('waiting', 'placing', 'active')
                ORDER BY created_at DESC
                LIMIT 1
            ''', user_id)

        return dict(row) if row else None

    async def update_multiplayer_stats(self, winner_id: int, loser_id: int):
        """Обновить статистику мультиплеера"""
        async with self.pool.acquire() as conn:
            await conn.execute('''
                INSERT INTO multiplayer_stats (user_id, opponent_id, games_played, games_won, games_lost, last_played_at)
                VALUES ($1, $2, 1, 1, 0, CURRENT_TIMESTAMP),
                       ($2, $1, 1, 0, 1, CURRENT_TIMESTAMP)
                ON CONFLICT (user_id, opponent_id) DO UPDATE SET
                    games_played = multiplayer_stats.games_played + 1,
                    games_won = CASE WHEN $1 = user_id THEN multiplayer_stats.games_won + 1 ELSE multiplayer_stats.games_won END,
                    games_lost = CASE WHEN $1 = user_id THEN multiplayer_stats.games_lost ELSE multiplayer_stats.games_lost + 1 END,
                    last_played_at = CURRENT_TIMESTAMP
            ''', winner_id, loser_id)

    async def get_multiplayer_stats(self, user_id: int) -> List[dict]:
        """Получить статистику мультиплеера пользователя"""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch('''
                SELECT ms.*, u.first_name as opponent_name
                FROM multiplayer_stats ms
                JOIN users u ON ms.opponent_id = u.user_id
                WHERE ms.user_id = $1
                ORDER BY ms.games_won DESC, ms.last_played_at DESC
                LIMIT 10
            ''', user_id)

        return [dict(row) for row in rows]

    async def check_frequent_games(self, user_id: int, opponent_id: int, max_per_day: int = 3) -> int:
        """Проверить частоту игр между игроками (защита от накрутки)"""
        async with self.pool.acquire() as conn:
            count = await conn.fetchval('''
                SELECT COUNT(*)
                FROM multiplayer_stats
                WHERE ((user_id = $1 AND opponent_id = $2)
                    OR (user_id = $2 AND opponent_id = $1))
                  AND last_played_at > CURRENT_TIMESTAMP - INTERVAL '1 day'
            ''', user_id, opponent_id)

        return count

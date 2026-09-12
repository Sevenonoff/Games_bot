-- Миграция для мультиплеера
-- Запуск: psql -U seafight_user -d seafight_bot -f migrations/add_multiplayer.sql

-- Таблица игр мультиплеера
CREATE TABLE IF NOT EXISTS multiplayer_games (
    game_id BIGSERIAL PRIMARY KEY,
    player1_id BIGINT NOT NULL,
    player2_id BIGINT,
    status VARCHAR(20) NOT NULL CHECK (status IN ('waiting', 'placing', 'active', 'finished', 'abandoned')),
    placement_complete1 BOOLEAN DEFAULT FALSE,
    placement_complete2 BOOLEAN DEFAULT FALSE,
    placement_mode VARCHAR(20) NOT NULL CHECK (placement_mode IN ('auto', 'manual')),
    current_turn BIGINT NOT NULL,
    turn_start_time TIMESTAMP,
    time_limit_seconds INTEGER,
    board1 TEXT NOT NULL,
    board2 TEXT NOT NULL,
    attacks1 TEXT,
    attacks2 TEXT,
    score1 INTEGER DEFAULT 0,
    score2 INTEGER DEFAULT 0,
    winner_id BIGINT,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    finished_at TIMESTAMP,
    last_move_time TIMESTAMP,
    timeouts_count1 INTEGER DEFAULT 0,
    timeouts_count2 INTEGER DEFAULT 0,
    FOREIGN KEY (player1_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (player2_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (winner_id) REFERENCES users(user_id)
);

-- Индексы для быстрого поиска
CREATE INDEX IF NOT EXISTS idx_multiplayer_games_player1 ON multiplayer_games(player1_id);
CREATE INDEX IF NOT EXISTS idx_multiplayer_games_player2 ON multiplayer_games(player2_id);
CREATE INDEX IF NOT EXISTS idx_multiplayer_games_status ON multiplayer_games(status);
CREATE INDEX IF NOT EXISTS idx_multiplayer_games_created_at ON multiplayer_games(created_at DESC);

-- Статистика мультиплеера
CREATE TABLE IF NOT EXISTS multiplayer_stats (
    id BIGSERIAL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    opponent_id BIGINT NOT NULL,
    games_played INTEGER DEFAULT 0,
    games_won INTEGER DEFAULT 0,
    games_lost INTEGER DEFAULT 0,
    last_played_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(user_id) ON DELETE CASCADE,
    FOREIGN KEY (opponent_id) REFERENCES users(user_id) ON DELETE CASCADE,
    UNIQUE(user_id, opponent_id)
);

CREATE INDEX IF NOT EXISTS idx_multiplayer_stats_user ON multiplayer_stats(user_id);

-- Комментарии
COMMENT ON TABLE multiplayer_games IS 'Игры мультиплеера морского боя';
COMMENT ON TABLE multiplayer_stats IS 'Статистика игрока в мультиплеере';

COMMENT ON COLUMN multiplayer_games.status IS 'Статус игры: waiting - ожидание второго игрока, placing - расстановка кораблей, active - игра идёт, finished - игра завершена, abandoned - игрок вышел';
COMMENT ON COLUMN multiplayer_games.placement_mode IS 'Режим расстановки: auto - автоматическая, manual - ручная';
COMMENT ON COLUMN multiplayer_games.current_turn IS 'ID игрока, чей сейчас ход';
COMMENT ON COLUMN multiplayer_games.time_limit_seconds IS 'Ограничение на ход в секундах (NULL = без ограничений)';

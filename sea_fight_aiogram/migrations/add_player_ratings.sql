-- Рейтинг игроков в мультиплеере (Elo), отдельный для каждого набора кораблей.
-- game_type: 'mp_full' | 'mp_reduced'
-- Стартовый рейтинг 1000, K-фактор 32 задан в коде (Database.RATING_DEFAULT / RATING_K).

CREATE TABLE IF NOT EXISTS player_ratings (
    user_id BIGINT NOT NULL REFERENCES users(user_id) ON DELETE CASCADE,
    game_type VARCHAR(20) NOT NULL,
    rating INTEGER NOT NULL DEFAULT 1000,
    games_played INTEGER NOT NULL DEFAULT 0,
    games_won INTEGER NOT NULL DEFAULT 0,
    games_lost INTEGER NOT NULL DEFAULT 0,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (user_id, game_type)
);

CREATE INDEX IF NOT EXISTS idx_player_ratings_top
    ON player_ratings(game_type, rating DESC);

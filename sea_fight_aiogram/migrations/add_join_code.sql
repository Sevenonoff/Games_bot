-- Миграция: добавление join_code для защиты ссылок
-- Запуск: psql -U seafight_user -d seafight_bot -f migrations/add_join_code.sql

ALTER TABLE multiplayer_games ADD COLUMN IF NOT EXISTS join_code VARCHAR(10);
CREATE INDEX IF NOT EXISTS idx_mp_games_join_code ON multiplayer_games(join_code);

-- Уникальный индекс для join_code (создаём отдельно чтобы не падать если есть дубли у пустых)
CREATE UNIQUE INDEX IF NOT EXISTS idx_mp_games_join_code_unique ON multiplayer_games(join_code) WHERE join_code IS NOT NULL;

COMMENT ON COLUMN multiplayer_games.join_code IS 'Уникальный код для подключения второго игрока (6 символов: A-Z0-9)';

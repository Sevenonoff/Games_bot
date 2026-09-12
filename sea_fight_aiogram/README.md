# Sea Fight Bot - Aiogram + PostgreSQL

Telegram бот "Морской бой" на aiogram 3.x с PostgreSQL базой данных.

## 📋 Особенности

- **Фреймворк:** aiogram 3.x
- **База данных:** PostgreSQL (asyncpg)
- **Игровое поле:** 8x8
- **Одиночная игра:** против поля со случайной расстановкой, анимация потопления
- **Мультиплеер:** игра с другом по ссылке-приглашению (код подключения)
  - выбор времени на ход (без лимита / 10с / 30с / 1м / 5м / 1ч);
    по таймауту ход переходит противнику, после 3 пропусков — техническое поражение
  - автоматическая или ручная расстановка кораблей (3 минуты на расстановку)
- **Наборы кораблей:** полный (4,3,3,2,2,2,1,1,1,1) и сокращённый (3,2,2,1,1,1)
- **Лидерборд:** отдельные таблицы для одиночной игры и мультиплеера по каждому набору
- **Мультиязычность:** Русский / Английский
- **Асинхронность:** Полностью асинхронная архитектура
- **Устойчивость к рестарту:** активные мультиплеерные игры и таймеры
  восстанавливаются из БД при запуске

## 🚀 Установка

### 1. Клонирование и установка зависимостей

```bash
cd /home/clawuser/projects/Games_bot/sea_fight_aiogram
pip install -r ../requirements.txt
```

### 2. Настройка переменных окружения

Скопируйте `.env.example` в `.env`:

```bash
cp .env.example .env
```

Отредактируйте `.env`:

```env
BOT_TOKEN=your_telegram_bot_token_here

# PostgreSQL configuration
DB_HOST=localhost
DB_PORT=5432
DB_NAME=seafight_bot
DB_USER=postgres
DB_PASSWORD=your_password_here
```

### 3. Создание базы данных PostgreSQL

```bash
# Подключение к PostgreSQL
sudo -u postgres psql

# Создание базы данных
CREATE DATABASE seafight_bot;

# Создание пользователя (если нужно)
CREATE USER seafight_user WITH PASSWORD 'your_password';
GRANT ALL PRIVILEGES ON DATABASE seafight_bot TO seafight_user;

# Выход
\q
```

### 4. Запуск бота

```bash
python main.py
```

## 📁 Структура проекта

```
sea_fight_aiogram/
├── main.py                    # Основной файл бота (одиночная игра + мультиплеер)
├── run.py                     # Скрипт запуска
├── config.py                  # Конфигурация (поле, символы, наборы кораблей)
├── states.py                  # FSM-состояния
├── .env.example               # Пример конфига
├── .env                       # Конфиг (не добавлять в git)
├── database/                  # Модуль базы данных
│   ├── database.py            # Database класс (asyncpg)
│   ├── models.py              # User, LeaderboardEntry
│   └── multiplayer_models.py  # MultiplayerGame, MultiplayerStats
├── keyboards/                 # Клавиатуры
│   └── keyboards.py
├── utils/                     # Утилиты
│   ├── game_logic.py          # Логика игры, генерация досок
│   ├── ship_placement.py      # Ручная расстановка кораблей
│   └── i18n.py                # Переводы (en/ru)
├── migrations/                # SQL-миграции (опционально — бот создаёт таблицы сам)
├── img/                       # Изображения
└── *.sh, seafight-bot.service # Скрипты запуска и systemd-юнит
```

## 🎮 Управление ботом

- `/start` — главное меню (или присоединение к игре по ссылке `?start=mp_КОД`)
- **Одиночная игра** — кнопка в меню: выбор набора кораблей и бой
- **Играть с другом** — кнопка в меню: выбор времени на ход, набора кораблей
  и режима расстановки, затем ссылка-приглашение для друга
- **Таблица рекордов** — кнопка в меню: четыре таблицы
  (одиночная/мультиплеер × полный/сокращённый набор)

## 💾 База данных

### Таблицы

#### `users`
- `user_id` (BIGINT PRIMARY KEY) - ID пользователя Telegram
- `first_name` (VARCHAR(255)) - Имя
- `last_name` (VARCHAR(255)) - Фамилия
- `username` (VARCHAR(255)) - Username
- `phone_number` (VARCHAR(20)) - Номер телефона
- `is_bot` (BOOLEAN) - Является ли ботом
- `language_code` (VARCHAR(10)) - Код языка
- `is_premium` (BOOLEAN) - Премиум пользователь
- `source` (VARCHAR(255)) - Источник приглашения
- `leaderboard_name` (VARCHAR(255)) - Имя для лидерборда
- `created_at` (TIMESTAMP) - Дата создания
- `updated_at` (TIMESTAMP) - Дата обновления

#### `leaderboard`
- `id` (SERIAL PRIMARY KEY) - ID записи
- `user_id` (BIGINT) - ID пользователя (FK)
- `name` (VARCHAR(255)) - Имя
- `score` (INTEGER) - Очки
- `game_type` (VARCHAR(20)) - Тип игры: `solo_full`, `solo_reduced`, `mp_full`, `mp_reduced`
- `created_at` (TIMESTAMP) - Дата создания

#### `multiplayer_games`
- `game_id` (SERIAL PRIMARY KEY) - ID игры
- `player1_id`, `player2_id` (BIGINT) - Игроки (FK на users)
- `status` (VARCHAR(20)) - `waiting`, `placing`, `active`, `finished`, `abandoned`
- `join_code` (VARCHAR(10)) - Уникальный код подключения (6 символов A-Z0-9)
- `placement_mode` (VARCHAR(10)) - `auto` / `manual`
- `ship_set` (VARCHAR(10)) - `full` / `reduced`
- `placement_complete1/2` (BOOLEAN) - Готовность расстановки
- `current_turn` (BIGINT) - Чей ход
- `time_limit_seconds` (INTEGER) - Лимит времени на ход (NULL — без лимита)
- `board1/2`, `attacks1/2` (JSONB) - Доски и история выстрелов
- `score1/2` (INTEGER) - Очки игроков
- `timeouts_count1/2` (INTEGER) - Пропуски хода (3 — техническое поражение)
- `winner_id`, `created_at`, `finished_at`, `last_move_time`, `turn_start_time`

#### `multiplayer_stats`
- Статистика пар игроков: `games_played`, `games_won`, `games_lost`, `last_played_at`

## 🔄 Перенос с python-telegram-bot

### Основные изменения:

1. **Фреймворк:** python-telegram-bot → aiogram 3.x
2. **База данных:** MySQL (mysql-connector) → PostgreSQL (asyncpg)
3. **Асинхронность:** Синхронный → Полностью асинхронный
4. **Конфигурация:** Прямое задание токена → .env файл
5. **Структура:** Монолитный файл → Модульная структура

### Ключевые улучшения:

- ✅ Асинхронная работа с БД через asyncpg
- ✅ Более быстрая и масштабируемая БД PostgreSQL
- ✅ Чистое разделение ответственности (MVC)
- ✅ Безопасное хранение токенов через .env
- ✅ Поддержка FSM для сложных сценариев

## 🛠️ Разработка

### Добавление новых переводов

Отредактируйте `utils/i18n.py`:

```python
translations = {
    'en': {
        'new_key': 'New text',
    },
    'ru': {
        'new_key': 'Новый текст',
    }
}
```

### Изменение размера поля

Отредактируйте `config.py`:

```python
ROWS = 10  # Количество строк
COLS = 10  # Количество столбцов
```

### Изменение конфигурации кораблей

Отредактируйте `config.py`:

```python
SHIPS = [4, 3, 3, 2, 2, 2, 1, 1, 1, 1]  # Размеры кораблей
```

## 📝 TODO

- [ ] Добавить тесты
- [ ] Добавить Docker поддержку
- [ ] Добавить миграции БД (alembic)
- [ ] Добавить администрирование
- [ ] Хранить FSM-состояния и одиночные игры вне памяти процесса (Redis),
      чтобы они переживали рестарт

## 📄 Лицензия

MIT

## 🤝 Вклад

Pull requests приветствуются!

## 📞 Контакты

Для вопросов и предложений: @Python_pars

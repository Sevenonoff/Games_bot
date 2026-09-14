# 📦 Установка и настройка Sea Fight Bot

## Требования

- Python 3.10 или выше
- PostgreSQL 12 или выше
- Telegram Bot Token

## Шаг 1: Установка зависимостей

```bash
cd /home/clawuser/projects/Games_bot/sea_fight_aiogram
pip install -r ../requirements.txt
```

## Шаг 2: Установка PostgreSQL (если не установлен)

### Ubuntu/Debian:
```bash
sudo apt update
sudo apt install postgresql postgresql-contrib
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

### CentOS/RHEL:
```bash
sudo yum install postgresql postgresql-server
sudo postgresql-setup initdb
sudo systemctl start postgresql
sudo systemctl enable postgresql
```

## Шаг 3: Создание базы данных

```bash
# Подключение к PostgreSQL
sudo -u postgres psql

# Внутри psql:
CREATE DATABASE seafight_bot;
CREATE USER seafight_user WITH PASSWORD 'your_secure_password';
GRANT ALL PRIVILEGES ON DATABASE seafight_bot TO seafight_user;
\q
```

## Шаг 4: Создание таблиц

Бот создаёт все таблицы (включая мультиплеер) и применяет миграции
автоматически при каждом запуске — отдельных действий не требуется.

SQL-файлы в `migrations/` оставлены для справки и ручного применения
при необходимости:

```bash
# Опционально, вручную:
psql -U postgres -d seafight_bot -f migrations/init.sql
psql -U postgres -d seafight_bot -f migrations/add_multiplayer.sql
psql -U postgres -d seafight_bot -f migrations/add_join_code.sql
```

## Шаг 5: Получение Telegram Bot Token

1. Найдите `@BotFather` в Telegram
2. Отправьте `/newbot`
3. Следуйте инструкциям для создания бота
4. Скопируйте полученный токен

## Шаг 6: Настройка .env файла

```bash
cp .env.example .env
nano .env
```

Заполните `.env`:

```env
BOT_TOKEN=ваш_токен_из_BotFather

DB_HOST=localhost
DB_PORT=5432
DB_NAME=seafight_bot
DB_USER=seafight_user
DB_PASSWORD=your_secure_password
```

## Шаг 7: Запуск бота

```bash
# Сделайте run.py исполняемым (опционально)
chmod +x run.py

# Запуск
python run.py
```

Или:

```bash
python main.py
```

## Шаг 8: Проверка работы

1. Откройте Telegram
2. Найдите своего бота
3. Отправьте `/start`
4. Игра должна начаться!

## 🔧 Troubleshooting

### Ошибка: "BOT_TOKEN не задан"

Бот проверяет токен при старте. Создайте `.env` по образцу:
```bash
cp .env.example .env
nano .env  # заполните BOT_TOKEN
```

### Ошибка: "FATAL: password authentication failed"

Решение:
```bash
sudo -u postgres psql
ALTER USER seafight_user WITH PASSWORD 'your_secure_password';
\q
```

### Ошибка: "connection refused"

Проверьте, запущен ли PostgreSQL:
```bash
sudo systemctl status postgresql
```

Если не запущен:
```bash
sudo systemctl start postgresql
```

### Ошибка: "database does not exist"

Создайте базу данных:
```bash
sudo -u postgres psql
CREATE DATABASE seafight_bot;
\q
```

### Ошибка: "No module named 'aiogram'"

Установите зависимости:
```bash
pip install -r ../requirements.txt
```

## 🚀 Запуск в фоне (screen/tmux)

### Используя screen:
```bash
screen -S seafight
python run.py
# Нажмите Ctrl+A, затем D для отсоединения

# Подключение:
screen -r seafight
```

### Используя tmux:
```bash
tmux new -s seafight
python run.py
# Нажмите Ctrl+B, затем D для отсоединения

# Подключение:
tmux attach -t seafight
```

### Используя systemd (для автозапуска):

Создайте файл `/etc/systemd/system/seafight-bot.service`:

```ini
[Unit]
Description=Sea Fight Telegram Bot
After=network.target postgresql.service

[Service]
Type=simple
User=clawuser
WorkingDirectory=/home/clawuser/projects/Games_bot/sea_fight_aiogram
ExecStart=/usr/bin/python3 /home/clawuser/projects/Games_bot/sea_fight_aiogram/run.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
```

Активируйте сервис:
```bash
sudo systemctl daemon-reload
sudo systemctl enable seafight-bot
sudo systemctl start seafight-bot

# Проверка статуса:
sudo systemctl status seafight-bot

# Просмотр логов:
sudo journalctl -u seafight-bot -f
```

## 📊 Мониторинг базы данных

```bash
# Подключение к базе
psql -U seafight_user -d seafight_bot

# Просмотр таблиц
\dt

# Просмотр пользователей
SELECT * FROM users LIMIT 10;

# Результаты одиночных партий (game_type: solo_full, solo_reduced)
SELECT * FROM leaderboard WHERE game_type = 'solo_full' ORDER BY score DESC LIMIT 10;

# Таблица рекордов одиночной игры так, как её видит игрок:
# лучший результат каждого, при равных очках выше более свежий
SELECT * FROM (
    SELECT DISTINCT ON (user_id) user_id, name, score, created_at
    FROM leaderboard WHERE game_type = 'solo_full'
    ORDER BY user_id, score DESC, created_at DESC
) t ORDER BY score DESC, created_at DESC LIMIT 10;

# Рейтинг мультиплеера (game_type: mp_full, mp_reduced)
SELECT user_id, rating, games_won, games_lost FROM player_ratings
WHERE game_type = 'mp_full' ORDER BY rating DESC LIMIT 10;

# Активные мультиплеерные игры
SELECT game_id, player1_id, player2_id, status, time_limit_seconds
FROM multiplayer_games WHERE status IN ('waiting', 'placing', 'active');

# Подсчет пользователей
SELECT COUNT(*) FROM users;

# Подсчет записей в лидерборде
SELECT COUNT(*) FROM leaderboard;

# Выход
\q
```

## 🔒 Безопасность

1. Не передавайте `.env` файл
2. Используйте сложные пароли для БД
3. Ограничьте доступ к базе данных по IP (при необходимости)
4. Регулярно делайте бэкапы базы данных

## 💾 Резервное копирование

```bash
# Бэкап базы данных
pg_dump -U seafight_user seafight_bot > backup_$(date +%Y%m%d).sql

# Восстановление из бэкапа
psql -U seafight_user seafight_bot < backup_20260101.sql
```

## 📝 Обновление

```bash
# Остановите бота
# Обновите код
git pull  # если используете git

# Обновите зависимости
pip install -r ../requirements.txt --upgrade

# Запустите бота — миграции применятся автоматически при старте
python run.py
```

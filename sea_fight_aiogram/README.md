# Бот игр для Telegram

Бот `@games_telegram_robot`. С 2.0.0 все игры идут из общего ядра `games_core` (корень репозитория), как у бота в Max (`max_bot/`):
- мемо, матрица памяти, башня чисел;
- морской бой: один и с другом (приглашение, таймер хода, ручная расстановка, рейтинг Elo).

Меню, экраны и правила одинаковы в обоих мессенджерах. Правила игр описаны в `max_bot/README.md`. Тексты пока только на русском.

## Как устроено
- `main.py` — точка входа: логирование, `Storage`, `Manager`, long polling.
- `games_tg.py` — транспорт aiogram для `Manager`. Он превращает `Screen` в сообщение и умеет три вещи:
  - отвечать на нажатие (правкой сообщения и уведомлением);
  - править сообщение по таймеру (`push`, ссылка на сообщение — `(chat_id, message_id)`);
  - присылать новое сообщение (`send`).
- Ссылка-приглашение в бой с другом — `https://t.me/<бот>?start=mp_<код>`, она приходит как `/start mp_<код>`. Код можно прислать и сообщением.
- `games_menu.py` — без aiogram:
  - кнопки ядра уходят с префиксом `g:`;
  - проверяются лимиты Telegram: до 8 кнопок в ряду, до 100 на клавиатуре, `callback_data` до 64 байт;
  - имя игрока: username → имя → id, без «@».
  Кнопки без `g:` из старых сообщений версии до 2.0.0 получают ответ «Эта кнопка устарела».
- Данные: SQLite `data/games.db`, `platform="tg"`. Там уровни, рекорды, рейтинг и незаконченные бои с другом; после перезапуска бои продолжаются вместе с таймерами.
- `deploy/migrate_postgres.py` — разовый перенос из PostgreSQL версии до 2.0.0 (выполнен 2026-10-19): игроки, рейтинг Elo, рекорды одиночного боя. Сама база `seafight_bot` в Postgres больше не используется, но не удалена.

## Запуск
Зависимости ставятся в отдельный venv бота: aiogram 3.13 несовместим с maxapi из корневого `.venv`.

```bash
python3 -m venv .venv
.venv/bin/pip install -r ../requirements.txt
cp .env.example .env              # BOT_TOKEN, LOG_FILE, DEBUG_USER_IDS
.venv/bin/python run.py           # вручную
```

Постоянно бот работает на 89.125.106.7 как user-сервис systemd (linger включён):

```bash
cp deploy/games-tg-bot.service ~/.config/systemd/user/
systemctl --user daemon-reload && systemctl --user enable --now games-tg-bot
systemctl --user status games-tg-bot     # restart / stop — так же
tail -f ../logs/tg_bot.log               # лог: каждое нажатие — строка tap
```

Вторую копию с тем же токеном запускать нельзя: Telegram отдаст `Conflict`.

## Тесты
- Игры, меню и бой с другом проверяются тестами ядра в корневом `.venv`:
  - сценарий меню TG — `tests/scenarios/tg_menu.scenario` (`Платформа: tg`);
  - бой с другом — `tests/scenarios/mp.scenario`;
  - на всех экранах проверяются лимиты Telegram.
- Связка с aiogram: `sea_fight_aiogram/.venv/bin/python -m pytest tests/test_tg_glue.py` (из корня репозитория).

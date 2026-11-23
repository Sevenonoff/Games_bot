# ТЗ M1. Ядро и сервер Mini App

Исполнитель: **Claude**. Документ нужен и исполнителям M2–M4: в нём точный контракт, по которому работает фронтенд.

## 1. Цель

Процесс `games-tg-bot` отдаёт Mini App: статику, картинки и WebSocket. Через WebSocket работают **все** экраны бота, а у экранов партий есть структурное состояние `view`.

## 2. Что сделать

### 2.1. `games_core/ui.py`
- `Screen.view: Optional[dict] = None`. `Screen.validate()` проверяет, что `view` сериализуется в JSON.
- Чат-транспорты (`max_bot/main.py`, `sea_fight_aiogram/games_tg.py`) поле не трогают.

### 2.2. `view` в экранах партий
`screen()` каждой партии заполняет `view` по схемам §3: `MemoSession`, `MatrixSession`, `TowerSession`, `PathSession` в `sessions.py` и `Multiplayer.screen()` в `multiplayer.py` (бой с другом и с компьютером, включая расстановку и ожидание). Текст и кнопки экрана не меняются: бот выглядит как раньше.

### 2.2а. Расстановка с ориентацией
В ядре корабль ставится «центр + поворот повторным нажатием». Если горизонтально в этой клетке корабль не встаёт, а вертикально встаёт, повернуть его нельзя. Для перетаскивания добавить payload `mpp:<код>:<r>:<c>:<h|v>` — поставить текущий корабль центром в клетку сразу в нужной ориентации (`Placement.place(center, vertical)`, те же проверки и ошибки). Старый `mpp:<код>:<r>:<c>` работает как прежде, у кнопок бота ничего не меняется.

### 2.3. Сервер `sea_fight_aiogram/webapp.py` (aiohttp, уже есть в venv бота как зависимость aiogram)
- `GET /app/` и `/app/assets/*` — сборка `miniapp/dist` (кэш: `index.html` — no-cache, `assets/*` — immutable).
- `GET /img/<sha1>.<jpg|png>` — картинки экранов (`Screen.image`): кэш в памяти, LRU на 300 штук, `Cache-Control: immutable`.
- `GET /ws` — WebSocket по протоколу из `README.md` §4.
- Слушает `127.0.0.1:${MINIAPP_PORT:-8447}`; наружу — через прокси из M5.

### 2.4. `sea_fight_aiogram/initdata.py`
`verify(init_data: str, bot_token: str, now: float, max_age=86400) -> Optional[dict]` — разбор и проверка подписи по документации Telegram («Validating data received via the Mini App»). Возвращает `user` (id, username, first_name) или `None`. Сравнение подписи — `hmac.compare_digest`.

### 2.5. Транспорт
- `msg_ref` Mini App: `("web", conn_id)`. `push` в `games_tg.build_manager` маршрутизирует по типу ссылки: кортеж из двух чисел — Telegram, `("web", …)` — соединение. Закрытого соединения нет — push молча пропускается (для `Manager` это как удалённое сообщение).
- `respond` для `press` шлёт `{"type":"screen","seq":…}` и возвращает `("web", conn_id)`. На одном соединении один экран, поэтому любой ответ «правит» его, как нажатие в чате правит своё сообщение. Уход с партии на другой экран отвязывает партию через существующий `detach`.
- `send(chat_id, screen)` (бот сам пишет игроку) идёт в чат, как сейчас. Если у игрока открыт Mini App, тот же экран дополнительно уходит в его соединения как `notice`.
- Игрок Mini App — тот же `Player(platform="tg", user_id, name, chat_id=user_id)`, что и в чате: одни уровни, рекорды и партии.
- Ссылка-приглашение в бой и в друзья для игрока из Mini App ведёт в Mini App: `https://t.me/<бот>/<app>?startapp=mp_<код>`. Имя приложения — `MINIAPP_SHORT_NAME`. Пока он не задан (до M5), ссылка остаётся старой, в чат.

### 2.6. Dev-режим
**Сделано.** Dev-сервер — `miniapp/dev-server.sh` (`sea_fight_aiogram/webapp_dev.py`): порт 8448, своя БД `miniapp/dev.db`, Telegram не поллит, вход только `dev_user` с localhost, `/dbg` для id 1. Боевой бот слушает 127.0.0.1:8447 (`MINIAPP_PORT`, пусто — выключить).
`MINIAPP_DEV=1` разрешает `{"type":"hello","dev_user":{…}}` с `127.0.0.1` и `localhost`. В проде переменная не задаётся.
В dev-режиме есть ещё `GET /dev/hint?user=<id>` → `{"payload": "t:…"}` — верный ход в текущей партии игрока (как `right_move` харнесса) для e2e-тестов фронтенда, и `/dbg`-команды для dev-пользователя с id из `DEBUG_USER_IDS`. Скрипт `miniapp/dev-server.sh` запускает сервер на тестовой БД **без поллинга Telegram**, чтобы не мешать боевому боту (правило: один поллер на токен).

### 2.7. Образцы `docs/miniapp/fixtures/`
Тест `tests/test_miniapp_fixtures.py` проводит партии на виртуальном времени и сохраняет кадр `screen` (с `view`) для каждого состояния из §3:
- игры: `memo-play`, `memo-mismatch`, `memo-done`, `matrix-countdown`, `matrix-preview`, `matrix-input`, `matrix-done`, `matrix-review`, `tower-countdown`, `tower-preview`, `tower-input`, `tower-review`, `path-countdown`, `path-preview`, `path-input`, `path-done`, `path-review`;
- морской бой: `sea-placement`, `sea-placement-current`, `sea-waiting-ready`, `sea-my-turn`, `sea-ai-thinking`, `sea-their-shot`, `sea-blink`, `sea-result`, `sea-invite`;
- экраны без `view`: `menu`, `sea-menu`, `ai-level`, `result-memo`.

Обычный прогон сверяет образцы с кодом. Если схема поменялась, образцы обновляются тем же коммитом: `UPDATE_FIXTURES=1 .venv/bin/python -m pytest tests/test_miniapp_fixtures.py`. Номер партии в образцах заменён на `a1b2c3`, картинки — на `/img/example.jpg`.

## 3. Схемы `view`

Общие поля (у всех `kind`):

| Поле | Тип | Смысл |
|---|---|---|
| `kind` | `"memo" \| "matrix" \| "tower" \| "path" \| "sea"` | какой компонент рисует экран |
| `title` | string | «🃏 Мемо» и т.п. |
| `actions` | `{[name]: string}` | шаблоны payload'ов, в них могут быть `{r}`, `{c}` |
| `level` | int | уровень (у морского боя нет) |
| `score` | int | очки партии |

### 3.1. Игры с раундами: `matrix`, `tower`, `path`
```json
{"kind": "matrix", "title": "🟦 Матрица памяти", "level": 6, "score": 140, "combo": "×2",
 "phase": "countdown" | "preview" | "input" | "review" | "done",
 "countdown": 3,
 "timer": {"left": 42, "total": 60, "overtime": false},
 "rounds": {"current": 2, "total": 6},
 "hint": "👆 Нажмите клетки, которые были синими",
 "grid": {"rows": 5, "cols": 4, "cells": [[{"k": "hidden"}, {"k": "shown"}, …], …]},
 "actions": {"tap": "t:a1b2c3:{r}:{c}", "quit": "q:a1b2c3", "skip": "t:a1b2c3:0:0"}}
```
- `timer` есть только у матрицы, `rounds` — только у поездки и дороги.
- `phase` и `countdown` — для анимации. Фазы переключает сервер (кадр `push`), клиент **не** ведёт свои таймеры фаз и может только плавно анимировать переход. Показ (`preview`) длится 1 с, отсчёт — 2 с на «3, 2, 1», разбор и итог — по 2 с.
- `done`/`review`: нажатие любой клетки — `actions.skip` (на `done` сервер переходит дальше).
- Ячейка `{"k": <вид>, "v": <текст>}`, где `v` — необязательный текст. Виды по играм:

| `kind` | `k` | Где |
|---|---|---|
| matrix | `hidden`, `shown` (синяя: показ или найденная), `answer` (зелёная: правильная, не найденная — на разборе), `wrong` (❌) | |
| tower | `inactive` (жёлтая, без числа, всегда), `hidden` (число скрыто), `number` (`v` — число), `wrong` (`v` — правильное число клетки, если есть) | `extra.road`: доля пути 0..1, `extra.km` — проехано км |
| path | `empty`, `block` (⛔), `step` (● дорога игрока), `answer` (🟡 кратчайшая — на разборе), `wrong`, `person` (`v` — эмодзи), `house` (`v` — эмодзи) | поле скрыто во время ввода: сервер сам не присылает `block`/`person`/`house` в фазе `input` |

### 3.2. Мемо
```json
{"kind": "memo", "title": "🃏 Мемо", "level": 4, "score": 60, "combo": "×1",
 "pairs": {"found": 3, "total": 8}, "moves": {"made": 9, "limit": 16},
 "done": false,
 "grid": {"rows": 4, "cols": 4, "cells": [[{"k": "back"}, {"k": "face", "v": "🐶"}, {"k": "matched", "v": "🐱"}, …]]},
 "actions": {"tap": "t:a1b2c3:{r}:{c}", "quit": "q:a1b2c3", "skip": "t:a1b2c3:0:0"}}
```
`face` — открыта сейчас, `matched` — найдена. Несовпавшая пара закрывается сама через 3 с (кадр `push`) или раньше — следующим нажатием.

### 3.3. Морской бой (`sea`) — с другом и с компьютером
```json
{"kind": "sea", "title": "⚔️ Морской бой", "code": "ABC234",
 "opponent": {"name": "🤖 Компьютер (продвинутый)", "ai": true},
 "set": "reduced", "status": "placing" | "waiting_ready" | "active" | "finished" | "waiting",
 "turn": "me" | "them" | null, "thinking": false,
 "timer": {"left": 27, "total": 30} | null, "timeouts": {"me": 0, "them": 1, "max": 3},
 "last": [{"by": "me", "result": "miss"}, {"by": "them", "result": "sunk"}],
 "own":   {"rows": 8, "cols": 7, "cells": [[{"k": "sea"}, {"k": "ship"}, {"k": "hit"}, {"k": "sunk"}, {"k": "miss"}]]},
 "enemy": {"rows": 8, "cols": 7, "cells": [[{"k": "sea"}, {"k": "miss"}, {"k": "hit"}, {"k": "sunk"}, {"k": "ship"}]]},
 "blink": {"board": "own" | "enemy", "cells": [[2, 3], [2, 4]], "frame": "hit" | "sunk"} | null,
 "result": {"won": true, "reason": "sunk" | "timeouts" | "surrender", "score": 90,
            "rating": 1016, "delta": 16, "journey": ["👣 +1 шаг · …"]} | null,
 "placement": {"sizes": [3, 2, 2, 1, 1, 1], "fixed": [[[0, 0], [0, 1], [0, 2]]], "current": [[4, 3], [4, 4]], "vertical": false,
               "forbidden": [[1, 0], …], "left": 154} | null,
 "actions": {"fire": "mpf:ABC234:{r}:{c}", "surrender": "mpg:ABC234",
             "place": "mpp:ABC234:{r}:{c}:{o}", "fix": "mpk:ABC234", "reset": "mpz:ABC234", "ready": "mpy:ABC234"}}
```
- `enemy.cells[*].k == "ship"` бывает только после итога: непотопленные корабли соперника открываются.
- `blink` — кадр мигания потопленного корабля (сервер шлёт 6 кадров по 0,4 с).
- `placement.vertical` — ориентация текущего корабля (`current`): `true` — вертикально.
- Перетаскивание на клиенте (M4) переводится в `place` (центр и ориентация `{o}` = `h` | `v`, см. §2.2а) и `fix`. Ошибка расстановки приходит `note`.
- Экран приглашения (`status: "waiting"`) несёт `invite: {"link": "…", "code": "ABC234"}`, а `actions.cancel_invite` — его отмену.

## 4. Тесты M1
- `tests/test_initdata.py`: верная подпись, подделанное поле, просроченная `auth_date`, мусор.
- `tests/test_webapp.py` (aiohttp test client, виртуальное время Manager): `hello` → меню; `press` с `seq` → ответ с тем же `seq`; таймер матрицы приходит `push` с `seq: null`; бой Mini App ↔ чат (один игрок в WebSocket, другой — в `Chat` харнесса) доходит до победы; разрыв соединения не роняет таймеры; `notice` при подключении соперника.
- `tests/test_miniapp_fixtures.py` (§2.7) и проверка JSON-сериализуемости `view` в `check_screen` харнесса — на каждом шаге случайного обхода.
- Существующие тесты и сценарии — без изменений и зелёные.

## 5. Готово, когда
- Все тесты зелёные, `fixtures/` сгенерированы.
- `miniapp/dev-server.sh` поднимает сервер с dev-входом; `websocat ws://127.0.0.1:8447/ws` проходит меню → мемо → ход.
- Чат-бот в TG и Max ведут себя как прежде (сценарии без изменений).

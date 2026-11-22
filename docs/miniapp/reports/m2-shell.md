# Отчёт M2. Каркас фронтенда Mini App

Ветка `miniapp/m2-shell` (от `main` = `289378a`; влит main с приёмкой 1). Коммиты: `9b1a63d` каркас, `d8d5238` vitest, `800860a` Playwright, отчёт. Доработка по `reviews/m2-shell-1.md` — раздел в конце.

## 1. Что сделано по пунктам ТЗ §3

| Пункт | Статус | Детали |
|---|---|---|
| §3.1 Структура | сделано | Все файлы из ТЗ на месте. Добавлены два служебных: `src/vite-env.d.ts` (типы vite для импорта css), `miniapp/env.d.ts` (минимальный `process.env` для конфигов — см. отступления) |
| §3.2 Подключение | сделано | `connection.ts`: адрес `location.origin` c `http→ws` и путём `/ws`; `hello` с `initData`/`start` или `dev_user` из `?dev_user=&dev_name=` (и `?start=` для проверки ссылок); `press` присваивает `seq`, нажатия не блокируются; переподключение 1-2-5-5 с, после восстановления `hello` без `start`; `error:auth` — экран «Откройте игры из Telegram» без повторов |
| §3.3 GenericScreen | сделано | Текст — разбор HTML-подмножества в дерево (`DOMParser`, белый список, `javascript:`/`onerror`/`script` выбрасываются) и рендер элементами Preact, без `innerHTML`; картинка во всю ширину с резервом 16:9 до загрузки и плавным появлением; ряд 1 кнопки — во всю ширину, 5–8 — сетка квадратных клеток; `noop` неактивен; `menu` дублируется `BackButton` на не-меню; нажатие — `selectionChanged()` + `press(data)`; `note` — toast на 1,5 с, «❌»/«Не ваш ход» → `notificationOccurred("error")`, иначе `impactOccurred("light")` |
| §3.4 Карточки notice | сделано | Bottom sheet поверх экрана: текст/картинка/кнопки тем же `GenericScreen`; кнопка шлёт `press` и закрывает, крестик закрывает; несколько карточек идут очередью |
| §3.5 Меню | сделано | Определение по кнопке `new:memo`; картинка пути сверху без отступов, скругление снизу; кнопки `new:*` и `sea` — плитками 2 в ряд (крупный первый символ подписи + название), остальные ряды как есть |
| §3.6 Тема | сделано | `themeParams` → `--bg`, `--text`, `--hint`, `--link`, `--button`, `--button-text`, `--secondary-bg`; подписка `themeChanged`; фон `--bg`, кнопки `--secondary-bg`, основная («Играть»/«Ещё раз»/«Новая партия…» — первая в последнем ряду) — `--button` |
| §3.7 registry | сделано | `GameProps<V>` и `games` ровно как в ТЗ; `App` берёт `games[view.kind]`, иначе `Placeholder` (GenericScreen + плашка «✨ Красивый экран игры — скоро»); `games` пуст — компоненты добавят M3/M4 |

## 2. Критерии приёмки §5

1. **Сборка**: `npm ci && npm run build` — без ошибок и предупреждений TypeScript (`strict: true`). Бандл **без картинок ≈ 13,8 КБ gzip** (JS 11,89 + CSS 1,45 + html 0,43), лимит 60 КБ.
2. **vitest — 49 тестов, зелёные** (хвост ниже): `html.ts` (белый список, `<script>`, `onerror=`, `javascript:`), `connection.ts` (рост `seq`, порядок применения, паузы 1-2-5-5, `hello` без `start`, auth), `GenericScreen` (ряды, клетки, `noop`, плитки меню, основная кнопка) и `App` (toast `note` + вибрация, `BackButton` на не-меню, полоса связи, очередь notice, auth-экран).
3. **Playwright — 20 тестов (5 сценариев × 4 проекта: 360×640/414×896 × светлая/тёмная), зелёные** (хвост ниже). `npm run e2e` = `npm run build && playwright test`; `webServer` поднимает `miniapp/dev-server.sh` на свежей временной БД (`DEV_DB=$(mktemp -d)/…`); у каждого теста свой `dev_user` (101–105, админ 1); `telegram-web-app.js` маршрутизируется в пустой ответ, вместо него `tests/e2e/fake-telegram.ts`; ход — по `GET /dev/hint`, нажимается кнопка с `data-payload`; сценарии из ТЗ все; скриншоты каждого шага — `miniapp/tests/e2e/__screenshots__/` (72 файла, в git не кладутся).
4. **В Telegram** — проверит Claude на M5 (не входило в M2).
5. **Код**: без `any` в `protocol.ts`; без глобального состояния вне `App` (сигналы создаются внутри `App`, `connection.ts` — только классы/функции); без `console.log` в сборке (в `src/` нет ни одного вызова `console`).

## 3. Отступления от ТЗ и их причины

1. **Разрыв соединения в e2e** (§5.3): `page.context().setOffline(true)` **не рвёт установленный WebSocket на localhost в Chromium** (проверено пробой: 8 с без `onclose`). Разрыв сделан перехватом `page.routeWebSocket()` (закрытие текущего сокета + отказ новым, пока «сети нет»); `setOffline` тоже вызывается — честно рвёт всё остальное. Замечание стоит учесть приёмке: сценарий из ТЗ буквальным `setOffline` на этой машине невоспроизводим.
2. **Порт e2e-сервера**: по ТЗ 8448. На этой машине порт занят форвардом VS Code (плагин, не наш процесс). Добавлена переменная `E2E_PORT` (по умолчанию 8448); прогон здесь — `E2E_PORT=8449 npm run e2e`. Конфиг и `fake-telegram.ts` берут её согласованно.
3. **`process.env` в конфигах**: `@playwright/test` начиная с актуальных версий не тянет `@types/node`, а его нет в списке зависимостей ТЗ. Вместо новой зависимости — `miniapp/env.d.ts` с минимальным объявлением `process` (только для чтения `E2E_PORT` в конфигах, `src` его не использует).
4. **Нажатия при разорванном соединении теряются, а не копятся** (в ТЗ не оговорено): очередь нажатий офлайн могла бы дать дубли при восстановлении (игрок повторит нажатие сам). Поведение «не блокируются» сохранено: каждое нажатие уходит немедленно, если сокет открыт.
5. **LD_LIBRARY_PATH для Chromium на Linux-машине** не вшит в `playwright.config.ts` (для этого нужен `process.platform`, см. п. 3): запускать `LD_LIBRARY_PATH=$HOME/.local/lib/playwright-deps npm run e2e` — переменная наследуется браузером.

## 4. Проблемы сервера и протокола

Существенных не найдено — контракт из `README.md` §4 и `tz-m1-core.md` §3 совпадает с фактическими кадрами сервера (сверено с `fixtures/` и живым dev-сервером). Мелкие наблюдения:

- `dbg:notify` присылает три карточки почти одновременно — очередь на клиенте обязательна (так и задумано, покрыто тестом).
- В `fixtures/menu.json` чёрные клетки мемо несут `data: "b:<sid>"`, а не `noop` — неактивными они не являются (сервер отвечает пустым `Reply`), клиент это никак не специаль-кейсит. Ожидаемо, просто фиксирую.

## 5. Окружение (не репозиторий)

- На машине не было `.venv`; создан `python3 -m venv --system-site-packages .venv`, доставлены `python-dotenv`, `aiogram`, `pillow` (psycopg2/asyncpg не нужны dev-серверу и тестам Mini App). `miniapp/dev-server.sh` работает как есть.
- `npm`/`node` этой машины не видят CA-бандл (brew-сборка), установка идёт с `NODE_EXTRA_CA_CERTS=/etc/ssl/cert.pem`.
- Питон-тесты репозитория: `404 passed, 188 skipped`; `tests/test_secret_filter.py` не собирается локально — нет пакета `maxapi` (SDK Max, вне requirements и вне M2; на сервере разработки он есть).

## 6. Вывод команд (хвосты)

`npm run build`:
```
dist/index.html                  0.65 kB │ gzip:  0.43 kB
dist/assets/index-C4I5M9l3.css   4.01 kB │ gzip:  1.45 kB
dist/assets/index-DMuhryNK.js   30.68 kB │ gzip: 11.89 kB
✓ built in 124ms
```

`npm test`:
```
 ✓ tests/unit/html.test.tsx (15 tests)
 ✓ tests/unit/connection.test.ts (15 tests)
 ✓ tests/unit/generic-screen.test.tsx (10 tests)
 ✓ tests/unit/app.test.tsx (10 tests)
 Test Files  4 passed (4)
      Tests  49 passed (49)
```

`npm run e2e` (20 = 5 × 4 проекта, здесь на порту 8449):
```
  ✓ [chromium-light-360] › tests/e2e/menu-memo.spec.ts (968ms)
  ✓ [chromium-light-360] › tests/e2e/friends-settings.spec.ts (944ms)
  … всего 20 строк ✓ …
  20 passed (10.6s)
```

## 7. Скриншоты e2e

`miniapp/tests/e2e/__screenshots__/`, 72 файла: `chromium-{light,dark}-{360,414}-<шаг>.png`. Шаги:
`01-menu`, `02-memo-board`, `03-memo-move`, `04-result`, `05-menu-again` (мемо);
`01-records-menu`, `02-records-memo`, `03-menu-again` (рекорды);
`01-friends`, `02-settings`, `03-settings-toggled`, `04-menu-again` (друзья/настройки);
`01-notice-friends`, `02-notice-reminder`, `03-notice-weekly`, `04-notice-done` (карточки);
`01-offline`, `02-reconnected` (связь).

## 8. Доработка 1 (по `docs/miniapp/reviews/m2-shell-1.md`)

Влит `origin/main` с приёмкой (правки ТЗ §3.5–3.6, `placement.vertical` в fixtures). По пунктам:

1. **Определение меню** — сделано. `isMenuScreen`: меню = экран с **обеими** кнопками `new:memo` и `sea`. Юнит-тест на кадре `fixtures/result-memo.json`: не меню, плиток нет, «Ещё раз» — обычная кнопка; в app-тестах меню-фикстура получила кнопку `sea`.
2. **Основная кнопка** — сделано. `primaryData`: первая кнопка экрана с подписью без эмодзи «Играть»/«Ещё раз»/«Новая партия…» в любом ряду. Тесты на кадрах `result-memo.json` (→ `new:memo`) и `sea-result.json` (→ `ai`); в e2e итога и рекордов основная кнопка проверяется на классе `primary`.
3. **Изоляция e2e** — сделано.
   - 3а: `userId(base, project)` = база теста + номер проекта (0…3); тесты используют базы 101/111/121/131; админ `dbg` — `1 + номер проекта`, в `webServer` добавлено `DEV_ADMINS="1 2 3 4"` (`dev-server.sh` не менялся).
   - 3б: все кнопки основного экрана ищутся внутри `mainScreen(page)` (`.app > .screen, .app > .placeholder`); перед шагами, где сервер мог прислать карточки, вызывается `dismissNotices(page)` (крестик, пока есть). Попутно найден подводный камень Playwright: цепочный `.locator(A).locator(B)` ищет только потомков A — атрибут на самом элементе A не находит, поэтому для плиток используются составные селекторы (`.tile[data-payload=…]`).
   - Проверка: `npx playwright test --repeat-each=3` — **60 passed** (5 сценариев × 4 проекта × 3 повтора), три прогона подряд зелёные.
4. **`placement.vertical: boolean`** — добавлен в `SeaView.placement` (`src/protocol.ts`), по `fixtures/sea-placement-current.json`.
5. **`cleanup.md`** — дописаны пути Linux: кэш Playwright `~/.cache/ms-playwright`, временные БД e2e `/tmp/tmp.*/`.

Хвост `npm test` после доработки:
```
 ✓ tests/unit/connection.test.ts (15 tests)
 ✓ tests/unit/html.test.tsx (14 tests)
 ✓ tests/unit/app.test.tsx (10 tests)
 ✓ tests/unit/generic-screen.test.tsx (13 tests)
 Test Files  4 passed (4)
      Tests  52 passed (52)
```

Хвост `npx playwright test --repeat-each=3` (порт 8449 из-за занятого 8448):
```
  ✓ [chromium-light-360] › tests/e2e/menu-memo.spec.ts … (×3)
  … всего 60 строк ✓ …
  60 passed (24.9s)
```

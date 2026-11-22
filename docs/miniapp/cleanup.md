# Очистка машины после разработки Mini App

Что появляется на машине при работе над `miniapp/` (M2–M4) и как это убрать.
Ничего глобального фронтенд не ставит: ни brew-пакетов, ни глобальных npm-модулей,
ни системных Python-библиотек — всё лежит в gitignored-каталогах проекта и в кэшах пользователя.

## Быстрая полная очистка (работа принята и слита)

Из корня репозитория:

```bash
# артефакты фронтенда и venv (gitignored, ~160 МБ)
rm -rf miniapp/node_modules miniapp/dist miniapp/test-results miniapp/playwright-report \
       miniapp/tests/e2e/__screenshots__ .venv

# браузер Playwright, скачанный под текущую версию @playwright/test (~210 МБ)
rm -rf ~/Library/Caches/ms-playwright/chromium_headless_shell-* ~/Library/Caches/ms-playwright/ffmpeg-*
# либо точечно из miniapp/: npx playwright uninstall chromium-headless-shell

# временные БД e2e-прогонов и логи (macOS; на Linux — /tmp)
rm -rf "${TMPDIR}"tmp.*/miniapp-e2e.db
rm -f /tmp/miniapp-e2e*.log

# ветка работы (если ещё не слита — не удалять!)
# git switch main && git branch -D miniapp/<часть>
```

Опционально — кэш npm (самоочищается, трогать обычно не нужно): `npm cache clean --force`.

## Постепенная очистка — что чем является

| Что | Размер | Путь | Когда можно убрать |
|---|---|---|---|
| Зависимости фронтенда | ~110 МБ | `miniapp/node_modules/` | когда больше не нужен `npm run build/test/e2e` (или после `npm ci` он пересоздастся сам) |
| Сборка | < 1 МБ | `miniapp/dist/` | пересоздаётся `npm run build`; нужна dev-серверу (`MINIAPP_STATIC`) |
| Скриншоты e2e | ~10 МБ | `miniapp/tests/e2e/__screenshots__/` | после приёмки (прикладываются к сдаче, в git не идут) |
| Отчёты Playwright | по мере прогонов | `miniapp/test-results/`, `miniapp/playwright-report/` | в любой момент |
| Venv бота/dev-сервера | ~50 МБ | `.venv/` (корень репозитория) | когда не нужен `miniapp/dev-server.sh` и питон-тесты; пересоздать: `python3 -m venv --system-site-packages .venv && .venv/bin/pip install python-dotenv aiogram pillow` |
| Chromium для Playwright | ~210 МБ | `~/Library/Caches/ms-playwright/chromium_headless_shell-<версия>/`, `ffmpeg-<версия>/` | если другие проекты Playwright не используют; **версии из чужих проектов лежат рядом** — удаляйте только папки с версией своего `@playwright/test` (номер — в `miniapp/node_modules/playwright-core/browsers.json`) |
| Кэш npm | растёт со временем | `~/.npm/_cacache/` | в любой момент, сам управляется |
| Временные БД e2e | копейки | `${TMPDIR}tmp.*/miniapp-e2e.db` (каждый прогон — новый каталог `mktemp -d`) | в любой момент; macOS чистит их сам |

## Dev-базы

- `miniapp/dev.db*` — база локального dev-сервера (`miniapp/dev-server.sh` без `DEV_DB`). Удаляется смело,
  при следующем запуске создастся заново (прогресс тестовых игроков обнулится).
- e2e всегда работает на одноразовой БД (`DEV_DB="$(mktemp -d)/miniapp-e2e.db"`) — боевой `dev.db` не трогает.

## Особенности машин

- **macOS (локальная)**: `npm`/`node` из brew не видят CA-бандл — установка идёт с
  `NODE_EXTRA_CA_CERTS=/etc/ssl/cert.pem`; это разовая переменная команды, в конфиги ничего не пишется.
  Порт dev-сервера 8448 может быть занят форвардом VS Code — e2e запускают с `E2E_PORT=<свободный порт>`.
- **Linux-сервер разработки (89.125.106.7)**: системные библиотеки Chromium подложены в
  `~/.local/lib/playwright-deps` — они стоят заранее и **не относятся к этой разработке, не удалять**.
  Запуск e2e: `LD_LIBRARY_PATH=$HOME/.local/lib/playwright-deps npm run e2e`.

## Что НЕ удалять, пока идёт разработка/приёмка

- ветку `miniapp/<часть>` до слияния;
- `miniapp/node_modules`, `.venv`, браузер Playwright — на них работают `npm run build && npm test && npm run e2e`
  и `miniapp/dev-server.sh`, которые запускает принимающий;
- `miniapp/package-lock.json` — он в git и нужен для `npm ci`.

# ТЗ M2. Каркас фронтенда Mini App

Исполнитель: **другая модель**. Приёмка: Claude по `acceptance.md`.
Перед началом прочитать `docs/miniapp/README.md` (архитектура, протокол) и `tz-m1-core.md` §3 (схемы `view`).

## 1. Цель

Приложение `miniapp/` открывается внутри Telegram, подключается к серверу по WebSocket и показывает **любой** экран бота: текст и кнопки в универсальном виде, а экраны с `view` — компонентом игры по `view.kind`. Компоненты игр делают M3 и M4; здесь — точка подключения и заглушка.

## 2. Стек и зависимости (только эти)

- `preact`, `@preact/signals`
- dev: `vite`, `@preact/preset-vite`, `typescript`, `vitest`, `@testing-library/preact`, `jsdom`, `@playwright/test`
- SDK Telegram подключается тегом `<script src="https://telegram.org/js/telegram-web-app.js">` в `index.html` (так требует Telegram). Типы — свой `src/telegram.d.ts` с нужным подмножеством.
- Без CSS-фреймворков, без роутера, без state-менеджеров. CSS — модули или один `app.css` с переменными.

Node 22 (есть на машине). `npm ci && npm run build` кладёт сборку в `miniapp/dist`, её отдаёт сервер M1 по `/app/` (`base: "/app/"` в Vite).

## 3. Что сделать

### 3.1. Структура
```
miniapp/
  index.html, package.json, vite.config.ts, tsconfig.json, playwright.config.ts
  src/main.tsx               вход: Telegram.WebApp.ready(), expand(), тема, монтирование <App/>
  src/protocol.ts            типы сообщений и view (README §4, tz-m1 §3) — ровно как в контракте
  src/connection.ts          WebSocket-клиент
  src/app/App.tsx            экран, toast, карточки notice, индикатор связи
  src/app/GenericScreen.tsx  универсальный рендер
  src/app/html.ts            безопасный рендер HTML-подмножества Telegram
  src/app/theme.ts           переменные CSS из themeParams
  src/games/registry.ts      kind → компонент; по умолчанию — GenericScreen
  src/games/Placeholder.tsx  заглушка для kind без компонента: GenericScreen + плашка «скоро»
  tests/unit/*.test.tsx      vitest
  tests/e2e/*.spec.ts        Playwright против dev-сервера M1
```

### 3.2. Подключение (`connection.ts`)
- Адрес: `location.origin` с заменой `http`→`ws`, путь `/ws`. Под `npm run dev` Vite проксирует `/ws`, `/img`, `/dev` на dev-сервер `http://127.0.0.1:8448` (настройка `server.proxy` с `ws: true`), так что адрес тот же.
- `hello` с `initData` из `Telegram.WebApp.initData` и `start` из `initDataUnsafe.start_param`. Объекта `window.Telegram` может не быть (страница открыта не в Telegram) — код это переживает.
- Вход без Telegram (разработка и e2e): если `initData` пуст и в адресе страницы есть `?dev_user=<id>&dev_name=<имя>`, в `hello` уходит `dev_user: {"id", "name"}` вместо `initData`. Работает и в собранной версии: безопасность обеспечивает сервер — он принимает `dev_user` только в dev-режиме и только с localhost. `start` для проверки ссылок — `?start=<param>`.
- `press(payload)` присваивает `seq` и шлёт кадр. Пока ответа на `press` нет, следующие нажатия **не блокируются**: сервер сам сериализует их под замком игрока. Ответы применяются в порядке прихода.
- Переподключение: паузы 1, 2, 5, 5… с; при восстановлении — `hello` без `start`. Индикатор «Нет связи…» — тонкая полоса сверху, появляется через 1 с после разрыва.
- `error: auth` — экран «Откройте игры из Telegram» без переподключения.

### 3.3. Универсальный рендер (`GenericScreen`)
- Текст: HTML-подмножество Telegram (`b`, `strong`, `i`, `em`, `u`, `s`, `code`, `pre`, `a[href]`, переносы строк). Всё остальное экранируется. **Без `innerHTML` с непроверенной строкой** — разбор в дерево и рендер элементами Preact.
- `image` — картинка во всю ширину над текстом в своих пропорциях (картинка пути — 16:9, открытки — свои), место под неё резервируется по `width`/`height` после загрузки без скачка вёрстки (до загрузки — 16:9), плавное появление.
- Кнопки — ряды как в `rows`. Ряд из одной кнопки — во всю ширину. Ряд из 5–8 кнопок — сетка квадратных клеток (игровое поле в старом виде). Высота кнопки ≥ 44 px, у клеток — по ширине экрана.
- Кнопка с `data == "noop"` — неактивная. `data == "menu"` дублируется системной кнопкой «Назад» Telegram (`BackButton`), когда экран не меню.
- Нажатие — `Telegram.WebApp.HapticFeedback.selectionChanged()` и `press(data)`.
- `note` — toast внизу на 1,5 с (новый заменяет старый). Если в `note` есть «❌» или «Не ваш ход», то `HapticFeedback.notificationOccurred("error")`, иначе `impactOccurred("light")`.

### 3.4. Карточки `notice`
Всплывают снизу поверх экрана (bottom sheet). В них текст, картинка и кнопки — тем же `GenericScreen`. Нажатие кнопки шлёт `press` и закрывает карточку; крестик просто закрывает. Несколько карточек идут очередью.

### 3.5. Меню
Меню приходит обычным экраном с картинкой пути (`image`). Универсального рендера достаточно, но:
- картинка пути — сверху, без отступов, со скруглением снизу;
- кнопки игр (`new:*`, `sea`) — плиткой 2 в ряд с крупным эмодзи (первый символ подписи) и названием. Остальные кнопки — как есть.
Определять «это меню» — по наличию кнопки с `data` `new:memo`.

### 3.6. Тема
`themeParams` → CSS-переменные (`--bg`, `--text`, `--hint`, `--link`, `--button`, `--button-text`, `--secondary-bg`). Подписка на `themeChanged`. Фон — `--bg`, кнопки — `--secondary-bg`, основная кнопка экрана (первая в последнем ряду, если это «Играть»/«Ещё раз»/«Новая партия…») — `--button`.

### 3.7. Подключение игр (`registry.ts`)
```ts
export type GameProps<V> = { view: V; screen: Screen; press: (payload: string) => void; note: string | null };
export const games: Partial<Record<View["kind"], ComponentType<GameProps<any>>>> = {};
```
`App` рисует `games[view.kind]`, если он есть, иначе `Placeholder`. M3/M4 только добавляют строки в `games`.

## 4. Не входит
Экраны игр (M3, M4), сервер (M1), хостинг (M5), офлайн-режим, локализация на другие языки.

## 5. Тесты и критерии приёмки
1. `npm run build` без предупреждений TypeScript (`strict: true`). Бандл без картинок ≤ 60 КБ gzip.
2. vitest:
   - `html.ts`: белый список тегов, `<script>`, `onerror=`, `javascript:` в `href` — экранируются или выбрасываются;
   - `connection.ts` (фейковый WebSocket): `seq` растёт, ответы применяются по порядку, переподключение с паузами, `hello` без `start` после разрыва;
   - `GenericScreen`: ряды, `noop`, toast `note`, `BackButton` на не-меню.
3. Playwright (`npm run e2e`, Chromium, вьюпорты 360×640 и 414×896, тёмная и светлая тема) против `miniapp/dev-server.sh` M1:
   - `npm run e2e` сам собирает приложение (`npm run build`) и поднимает dev-сервер через `webServer` в `playwright.config.ts`: `DEV_DB` — свежий временный файл на каждый прогон, адрес `http://127.0.0.1:8448/app/?dev_user=<id>&dev_name=<имя>`. Сборка — до старта сервера: папку `dist/assets` сервер подхватывает при запуске;
   - у каждого теста свой `dev_user` (у игрока одна открытая партия и свои рекорды — тесты не должны мешать друг другу). Id 1 — админ с `/dbg`;
   - скрипт `telegram-web-app.js` в тестах не грузится с telegram.org (`page.route` → пустой ответ). Вместо него `tests/e2e/fake-telegram.ts` подкладывает `window.Telegram.WebApp` с `initData: ""`, `themeParams` (светлая и тёмная палитры), заглушками `ready/expand/BackButton/HapticFeedback/onEvent` и счётчиками вызовов для проверок;
   - ход в партии — по подсказке сервера: `GET http://127.0.0.1:8448/dev/hint?user=<id>` → `{"payload": "t:…" | null}`, затем `press(payload)` через нажатие соответствующей клетки на экране (тест ищет кнопку с таким `data`; атрибут `data-payload` на кнопках разрешён);
   - сценарии: меню → «Мемо» → ход → «Закончить» → итог → «Меню»; меню → «Рекорды» → «Мемо» → «Меню»; «Мои друзья» и «Настройки» открываются и возвращаются; карточки `notice`: админ шлёт `press("dbg:notify")` (бот присылает уведомление друзей, напоминание и итоги недели) → карточки идут очередью, кнопка карточки работает, крестик закрывает; разрыв соединения (`page.context().setOffline(true)` → полоса «Нет связи» → `setOffline(false)` → меню);
   - скриншоты каждого шага в `tests/e2e/__screenshots__/` (прикладываются к сдаче, в git не кладутся — в `.gitignore`).
4. В Telegram (проверит Claude на этапе M5): открывается кнопкой бота, тема совпадает, «Назад» работает.
5. Код: без `any` в `protocol.ts`, без глобального состояния вне `App`, без `console.log` в сборке.

## 6. Как сдавать
Ветка `miniapp/m2-shell` от актуальной основной ветки. В отчёте: что сделано по пунктам §3, отступления от ТЗ с причинами, скриншоты, вывод `npm test` и `npm run e2e`.

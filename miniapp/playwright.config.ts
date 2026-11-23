import { defineConfig } from "@playwright/test";

// `npm run e2e` сначала собирает приложение (dist/), затем поднимает dev-сервер M1
// на свежей временной БД — папку dist/assets сервер подхватывает при запуске.
// У каждой пары «тест + проект» свой dev_user (fake-telegram.ts), админы для dbg-теста —
// DEV_ADMINS="1 2 3 4", по одному на проект: параллельные окна не мешают друг другу.
// Порт 8448 по ТЗ; если он занят (например, форвардом на другую машину) — E2E_PORT=… npm run e2e.
// На машине разработки Chromium берёт системные библиотеки из LD_LIBRARY_PATH
// окружения запуска (на Linux: LD_LIBRARY_PATH=$HOME/.local/lib/playwright-deps npm run e2e).
import { PROJECTS } from "./tests/e2e/fake-telegram";

const port = Number(process.env.E2E_PORT ?? "8448");

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  // Потоков — по умолчанию Playwright (половина ядер): на машине 89.125.106.7 (2 ядра, 2 ГБ)
  // четыре Chromium разом съедают память и тесты виснут (приёмка M2-2). Больше — E2E_WORKERS=4.
  workers: process.env.E2E_WORKERS ? Number(process.env.E2E_WORKERS) : undefined,
  retries: 0,
  reporter: [["list"]],
  outputDir: "./test-results",
  use: {
    actionTimeout: 5_000,
  },
  projects: PROJECTS.map((p) => ({ name: p.name, use: { viewport: p.viewport } })),
  webServer: {
    command: `bash -c 'DEV_ADMINS="1 2 3 4" DEV_DB="$(mktemp -d)/miniapp-e2e.db" DEV_PORT=${port} ./dev-server.sh'`,
    url: `http://127.0.0.1:${port}/app/`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});

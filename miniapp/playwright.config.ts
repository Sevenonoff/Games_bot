import { defineConfig } from "@playwright/test";

// `npm run e2e` сначала собирает приложение (dist/), затем поднимает dev-сервер M1
// на свежей временной БД — папку dist/assets сервер подхватывает при запуске.
// Каждый тест ходит своим dev_user, поэтому прогоны не мешают друг другу.
// Порт 8448 по ТЗ; если он занят (например, форвардом на другую машину) — E2E_PORT=… npm run e2e.
// На машине разработки Chromium берёт системные библиотеки из LD_LIBRARY_PATH
// окружения запуска (на Linux: LD_LIBRARY_PATH=$HOME/.local/lib/playwright-deps npm run e2e).

const port = Number(process.env.E2E_PORT ?? "8448");

export default defineConfig({
  testDir: "./tests/e2e",
  timeout: 30_000,
  expect: { timeout: 5_000 },
  fullyParallel: true,
  workers: 4,
  retries: 0,
  reporter: [["list"]],
  outputDir: "./test-results",
  use: {
    actionTimeout: 5_000,
  },
  projects: [
    { name: "chromium-light-360", use: { viewport: { width: 360, height: 640 } } },
    { name: "chromium-light-414", use: { viewport: { width: 414, height: 896 } } },
    { name: "chromium-dark-360", use: { viewport: { width: 360, height: 640 } } },
    { name: "chromium-dark-414", use: { viewport: { width: 414, height: 896 } } },
  ],
  webServer: {
    command: `bash -c 'DEV_DB="$(mktemp -d)/miniapp-e2e.db" DEV_PORT=${port} ./dev-server.sh'`,
    url: `http://127.0.0.1:${port}/app/`,
    reuseExistingServer: false,
    timeout: 60_000,
  },
});

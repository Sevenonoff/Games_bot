// Морской бой, e2e (tz-m4 §8.3): бой с компьютером до победы (dbg:sea_end), обычный бой,
// ручная расстановка перетаскиванием, бой с другом в двух контекстах. id: 400–499 игроки,
// 500–599 админы (userId из fake-telegram: base + номер проекта).
import { expect, test, type Page } from "@playwright/test";
import {
  APP_ORIGIN, dismissNotices, hint, mainScreen, openApp, serverPress, shot, themeOf, userId,
} from "./fake-telegram";
import type { Theme } from "./fake-telegram";

/** serverPress с повтором: сразу после старта webServer соединение может не успеть. */
async function serverPressSafe(page: Page, user: number, payload: string): Promise<void> {
  for (let attempt = 0; ; attempt++) {
    try {
      await serverPress(page, user, payload);
      return;
    } catch (e) {
      if (attempt >= 2) throw e;
      await page.waitForTimeout(1000);
    }
  }
}

/** Второй игрок входит по ссылке-приглашению: ?dev_user=…&start=mp_<код> (tz-m4 §8.3). */
async function openAppWithStart(
  page: Page, user: number, name: string, theme: Theme, start: string,
): Promise<void> {
  await page.route(/telegram-web-app\.js$/, (route) =>
    route.fulfill({ status: 200, contentType: "application/javascript", body: "" }));
  await page.addInitScript(() => {
    window.Telegram = {
      WebApp: {
        initData: "", initDataUnsafe: { start_param: "MP_TEST" }, themeParams: {},
        ready() {}, expand() {}, onEvent() {},
        BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
        HapticFeedback: { selectionChanged() {}, notificationOccurred() {}, impactOccurred() {} },
        showConfirm: (_t: string, cb?: (ok: boolean) => void) => cb?.(true),
        openTelegramLink() {},
      },
    };
  });
  const url = new URL("/app/", APP_ORIGIN);
  url.searchParams.set("dev_user", String(user));
  url.searchParams.set("dev_name", name);
  url.searchParams.set("start", start);
  await page.goto(url.toString());
}

const RESULT = "Партия окончена";

/** Клик по клетке поля соперника с данным data-payload (внутри основного экрана). */
async function clickCell(page: Page, payload: string): Promise<void> {
  await mainScreen(page).locator(`button[data-payload="${payload}"]`).first().click();
}

/** Перетащить корабль из дока (первый) в клетку-центр поля расстановки. */
async function dragFromDock(page: Page, r: number, c: number): Promise<void> {
  const board = mainScreen(page).locator(".placing-board");
  const cellRect = await board.locator(".scell").first().boundingBox();
  expect(cellRect).not.toBeNull();
  const nextRect = await board.locator(".scell").nth(1).boundingBox();
  const stride = nextRect!.x - cellRect!.x;
  const ship = mainScreen(page).locator(".dock-ship").first();
  const shipRect = await ship.boundingBox();
  // путь: взял → несколько промежуточных точек → центр клетки-цели → отпустил
  const tx = cellRect!.x + c * stride + cellRect!.width / 2;
  const ty = cellRect!.y + r * stride + cellRect!.height / 2;
  await page.mouse.move(shipRect!.x + shipRect!.width / 2, shipRect!.y + shipRect!.height / 2);
  await page.mouse.down();
  await page.mouse.move(tx - 40, ty - 30, { steps: 5 });
  await page.mouse.move(tx, ty, { steps: 5 });
  await page.mouse.up();
}

/** Центры кораблей малого набора [3,2,2,1,1,1]: без соприкосновений (запреты вокруг). */
const MANUAL_CENTERS: Array<[number, number]> = [
  [0, 1], [2, 1], [4, 1], [6, 1], [6, 4], [7, 6],
];

test("бой с компьютером до победы: dbg:sea_end → выстрел → итог → мастер", async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  const admin = userId(500, testInfo.project.name);
  await openApp(page, admin, "Админ", themeOf(testInfo.project.name));
  const screenEl = mainScreen(page);
  await expect(screenEl.locator('.tile[data-payload="sea"]')).toBeVisible();
  // dbg после открытия страницы: serverPress шлёт ws с location.host этой страницы
  await serverPressSafe(page, admin, "dbg:sea_end:reduced"); // партия за выстрел до победы
  await screenEl.locator('.tile[data-payload="sea"]').click();
  await expect(screenEl.locator('button[data-payload="mpb"]')).toBeVisible();   // «Вернуться к партии» (без кода)
  await screenEl.locator('button[data-payload="mpb"]').click();
  await expect(page.locator('.game-sea[data-status="active"][data-turn="me"]')).toBeVisible({ timeout: 8000 });
  await shot(page, testInfo, "01-before-win");

  const payload = await hint(admin);
  expect(payload).toMatch(/^mpf:/);
  await clickCell(page, payload!);

  await expect(page.locator(".result-card")).toBeVisible({ timeout: 20_000 });
  await expect(page.locator(".result-card")).toContainText("Победа");
  await shot(page, testInfo, "02-result");

  // «🤖 Новая партия с компьютером» открывает мастер выбора сложности
  const again = screenEl.locator('button[data-payload="ai"]');
  await expect(again).toBeVisible();
  await again.click();
  await expect(screenEl.locator('button[data-payload^="ain:normal"]')).toBeVisible();
  await shot(page, testInfo, "03-ai-level");
});

test("обычный бой: мастер → выстрел → ответ компьютера", async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  const user = userId(400, testInfo.project.name);
  await openApp(page, user, "Анна", themeOf(testInfo.project.name));
  const screenEl = mainScreen(page);
  await screenEl.locator('.tile[data-payload="sea"]').click();
  await screenEl.locator('button[data-payload="ai"]').click();
  await screenEl.locator('button[data-payload="ain:normal"]').click();
  await screenEl.locator('button[data-payload="ain:normal:0"]').click();          // без лимита
  await screenEl.locator('button[data-payload="ain:normal:0:reduced"]').click();  // малый набор
  await screenEl.locator('button[data-payload="ain:normal:0:reduced:auto"]').click();  // авто-расстановка

  await expect(page.locator('.game-sea[data-status="active"]')).toBeVisible({ timeout: 8000 });
  await shot(page, testInfo, "01-battle");

  // пара выстрелов по подсказке; после каждого компьютер отвечает (думает 1 с) — ждём своего хода
  for (let i = 0; i < 3; i++) {
    const payload = await hint(user);
    if (payload === null) {
      await page.waitForTimeout(400);
      continue;
    }
    await clickCell(page, payload);
    if (i === 0) await shot(page, testInfo, "02-my-shot");
    await expect(page.locator('.game-sea[data-turn="me"]')).toBeVisible({ timeout: 15_000 });
  }
  await shot(page, testInfo, "03-after-round");

  await dismissNotices(page);
  await screenEl.locator('button[data-payload^="mpg:"]').click();   // сдача — фейковый showConfirm «ОК»
  await expect(page.locator(".result-card")).toContainText("Поражение", { timeout: 20_000 });
  await shot(page, testInfo, "04-result");
});

test("ручная расстановка перетаскиванием полного набора → Готов → бой", async ({ page }, testInfo) => {
  test.setTimeout(180_000);
  const user = userId(410, testInfo.project.name);
  await openApp(page, user, "Борис", themeOf(testInfo.project.name));
  const screenEl = mainScreen(page);
  await screenEl.locator('.tile[data-payload="sea"]').click();
  await screenEl.locator('button[data-payload="ai"]').click();
  await screenEl.locator('button[data-payload="ain:normal"]').click();
  await screenEl.locator('button[data-payload="ain:normal:0"]').click();
  await screenEl.locator('button[data-payload="ain:normal:0:reduced"]').click();
  await screenEl.locator('button[data-payload="ain:normal:0:reduced:manual"]').click();

  await expect(page.locator('.game-sea[data-status="placing"]')).toBeVisible({ timeout: 8000 });
  await expect(screenEl.locator(".dock-ship")).toHaveCount(6);   // малый набор: 3,2,2,1,1,1
  await shot(page, testInfo, "01-placing");

  for (let i = 0; i < MANUAL_CENTERS.length; i++) {
    const [r, c] = MANUAL_CENTERS[i]!;
    await dragFromDock(page, r, c);
    // сервер подтвердил: док уменьшился на один корабль
    await expect(screenEl.locator(".dock-ship")).toHaveCount(6 - i - 1, { timeout: 8000 });
  }
  await expect(screenEl.locator(".dock-empty")).toContainText("Все корабли на месте");
  await shot(page, testInfo, "02-placed");

  const ready = screenEl.locator('button[data-payload^="mpy:"]');
  await expect(ready).toBeVisible({ timeout: 5000 });            // «Готов» появляется, когда всё стоит
  await ready.click();
  await expect(page.locator('.game-sea[data-status="active"]')).toBeVisible({ timeout: 20_000 });
  await shot(page, testInfo, "03-battle");
});

test("бой с другом: приглашение, вход по ссылке, выстрелы, сдача", async ({ page }, testInfo) => {
  test.setTimeout(180_000);
  const host = userId(420, testInfo.project.name);
  const guest = userId(430, testInfo.project.name);
  const theme = themeOf(testInfo.project.name);

  // первый: приглашение
  await openApp(page, host, "Вера", theme);
  const hostScreen = mainScreen(page);
  await hostScreen.locator('.tile[data-payload="sea"]').click();
  await hostScreen.locator('button[data-payload="mp"]').click();
  await hostScreen.locator('button[data-payload="mpn:0"]').click();              // без лимита
  await hostScreen.locator('button[data-payload="mpn:0:reduced"]').click();
  await hostScreen.locator('button[data-payload="mpn:0:reduced:auto"]').click();
  await expect(page.locator(".invite-code")).toBeVisible({ timeout: 8000 });
  const code = (await page.locator(".invite-code").textContent())!.trim();
  expect(code).toMatch(/^[A-Z0-9]{6}$/);
  await shot(page, testInfo, "01-invite");

  // второй: вход по ссылке-приглашению
  const page2 = await page.context().newPage();
  await openAppWithStart(page2, guest, "Гоша", theme, `mp_${code}`);
  await expect(page2.locator('.game-sea[data-status="active"][data-turn="them"]')).toBeVisible({ timeout: 20_000 });
  await expect(page.locator('.game-sea[data-status="active"][data-turn="me"]')).toBeVisible({ timeout: 20_000 });
  await shot(page, testInfo, "02-battle-host");

  // по выстрелу у каждого
  const hostPayload = await hint(host);
  expect(hostPayload).toMatch(/^mpf:/);
  await clickCell(page, hostPayload!);
  await expect(page.locator('.game-sea[data-turn="them"]')).toBeVisible({ timeout: 15_000 });
  await shot(page2, testInfo, "03-battle-guest");
  const guestPayload = await hint(guest);
  if (guestPayload !== null) {
    await mainScreen(page2).locator(`button[data-payload="${guestPayload}"]`).first().click();
    await expect(page.locator('.game-sea[data-turn="me"]')).toBeVisible({ timeout: 15_000 });
  }

  // сдача первого (showConfirm фейка отвечает «ОК») → у второго карточка победы
  await dismissNotices(page);
  await hostScreen.locator('button[data-payload^="mpg:"]').click();
  await expect(page2.locator(".result-card")).toContainText("Победа", { timeout: 15_000 });
  await shot(page2, testInfo, "04-guest-wins");
  await expect(hostScreen.locator(".result-card")).toContainText("Поражение", { timeout: 20_000 });
  await shot(page, testInfo, "05-host-loses");
  await page2.close();
});

// Мемо, e2e (tz-m3 §7.3): полная партия по подсказке, несовпавшая пара, поле 14×7
// максимального уровня, 10 партий подряд без роста DOM. id: игроки 201–204, админ 300+.
import { expect, test } from "@playwright/test";
import { adminId, playerId } from "./m3-ids";
import {
  dismissNotices, hint, mainScreen, openApp, projectIndex, serverPress, shot, themeOf,
} from "./fake-telegram";

const RESULT = "Партия окончена";


/** Клик по клетке с данным data-payload внутри основного экрана (tz-m3 §1.2). */
async function clickCell(page: import("@playwright/test").Page, payload: string): Promise<void> {
  await mainScreen(page).locator(`button[data-payload="${payload}"]`).first().click();
}

async function startMemo(page: import("@playwright/test").Page, user: number, name: string, theme: string) {
  await openApp(page, user, name, themeOf(theme));
  const screenEl = mainScreen(page);
  await screenEl.locator('.tile[data-payload="new:memo"]').click();
  await expect(page.locator(".game-memo")).toBeVisible();
  return screenEl;
}

test("полная партия от меню до итога", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  const user = playerId(0, projectIndex(testInfo.project.name), testInfo.repeatEachIndex);
  const screenEl = await startMemo(page, user, "Анна", testInfo.project.name);
  await expect(page.locator('.game-memo[data-phase="play"]')).toBeVisible();
  await shot(page, testInfo, "01-play");

  let doneShot = false;
  for (let i = 0; i < 120; i++) {
    if (await page.getByText(RESULT).isVisible({ timeout: 50 }).catch(() => false)) break;
    if (!doneShot && await page.locator('.game-memo[data-phase="done"]').isVisible({ timeout: 50 }).catch(() => false)) {
      await shot(page, testInfo, "03-done");
      doneShot = true;
    }
    const payload = await hint(user);
    if (payload === null) {
      await page.waitForTimeout(300);
      continue;
    }
    await clickCell(page, payload);
    if (i === 1) await shot(page, testInfo, "02-mid-play");   // пара ходов сделана
    await page.waitForTimeout(120);
  }
  await expect(page.getByText(RESULT)).toBeVisible({ timeout: 10_000 });
  await dismissNotices(page);
  await shot(page, testInfo, "04-result");
});

test("несовпавшая пара закрывается кадром сервера", async ({ page }, testInfo) => {
  test.setTimeout(60_000);
  const user = playerId(1, projectIndex(testInfo.project.name), testInfo.repeatEachIndex);
  const screenEl = await startMemo(page, user, "Борис", testInfo.project.name);

  const first = await hint(user);
  expect(first).toMatch(/^t:/);
  await screenEl.locator(`button[data-payload="${first}"]`).click();   // открыли одну карту
  await expect(page.locator(".game-memo .k-face")).toHaveCount(1);     // кадр пришёл, карта перевернулась

  const pair = await hint(user);                                        // подсказка — её пара
  expect(pair).toMatch(/^t:/);
  const face = await page.locator(".game-memo .k-face").first().getAttribute("data-payload");
  const other = screenEl.locator(
    `.card.k-back:not([data-payload="${pair}"]):not([data-payload="${face}"])`).first();
  await other.click();                                                  // ошиблись второй картой

  await expect(page.locator(".game-memo .k-face")).toHaveCount(2, { timeout: 5000 });
  await shot(page, testInfo, "01-mismatch");
  await expect(page.locator(".game-memo .k-face")).toHaveCount(0, { timeout: 8000 });   // сервер закрыл через 3 с
  await shot(page, testInfo, "02-closed");

  await dismissNotices(page);
  await screenEl.locator('button[data-payload^="q:"]').click();         // «Закончить»
  await expect(page.getByText(RESULT)).toBeVisible({ timeout: 5000 });
  await shot(page, testInfo, "03-result");
});

test("поле максимального уровня 14×7 влезает без прокрутки", async ({ page }, testInfo) => {
  const admin = adminId(0, projectIndex(testInfo.project.name), testInfo.repeatEachIndex);
  await openApp(page, admin, "Админ", themeOf(testInfo.project.name));
  const screenEl = mainScreen(page);
  await expect(screenEl.locator(".tile").first()).toBeVisible();
  await serverPress(page, admin, "dbg:level:memo:40");   // уровень ставим ДО партии: dbg прерывает открытую
  await screenEl.locator('.tile[data-payload="new:memo"]').click();
  await expect(page.locator(".game-memo")).toBeVisible({ timeout: 5000 });

  const metrics = await page.evaluate(() => ({
    hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    // верхний ряд достижим: при прокрутке в начало он не уходит под край зоны
    topCut: (() => {
      const zone = document.querySelector<HTMLElement>(".game .field-scroll")!;
      zone.scrollTop = 0;
      const cell = document.querySelector<HTMLElement>(".game .gcell")!;
      return zone.getBoundingClientRect().top - cell.getBoundingClientRect().top;
    })(),
    cell: document.querySelector<HTMLElement>(".game-memo .gcell")?.getBoundingClientRect().width ?? 0,
    cells: document.querySelectorAll(".game-memo .gcell").length,
  }));
  expect(metrics.hscroll).toBe(false);
  expect(metrics.topCut).toBeLessThanOrEqual(0);
  expect(metrics.cell).toBeGreaterThanOrEqual(30);
  expect(metrics.cells).toBe(14 * 7);
  await shot(page, testInfo, "01-big-field");
});

test("10 партий подряд не растят DOM", async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  const user = playerId(2, projectIndex(testInfo.project.name), testInfo.repeatEachIndex);
  const screenEl = await startMemo(page, user, "Вера", testInfo.project.name);
  await expect(page.locator(".game-memo .gcell").first()).toBeVisible();
  const first = await page.evaluate(() => document.querySelectorAll("*").length);

  for (let i = 0; i < 9; i++) {
    await dismissNotices(page);
    await screenEl.locator('button[data-payload^="q:"]').click();
    await expect(page.getByText(RESULT)).toBeVisible({ timeout: 5000 });
    await page.locator('button[data-payload="new:memo"]').first().click();   // «🔁 Ещё раз»
    await expect(page.locator(".game-memo .gcell").first()).toBeVisible({ timeout: 5000 });
  }
  const last = await page.evaluate(() => document.querySelectorAll("*").length);
  expect(last).toBeLessThanOrEqual(Math.ceil(first * 1.1));   // не больше чем +10%
});

// Поездка на числах, e2e (tz-m3 §7.3): партия с дорогой и км, ошибка, поле 14×7 (уровень 80).
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


async function startTower(page: import("@playwright/test").Page, user: number, name: string, projectName: string) {
  await openApp(page, user, name, themeOf(projectName));
  const screenEl = mainScreen(page);
  await screenEl.locator('.tile[data-payload="new:tower"]').click();
  await expect(page.locator(".game-tower")).toBeVisible({ timeout: 5000 });
  return screenEl;
}

/** Закрытая числовая клетка, кроме подсказки: в начале ввода следующее число тоже
 *  скрыто — ошибкой будет любая ДРУГАЯ закрытая (порядок не тот). */
async function otherHidden(page: import("@playwright/test").Page, notPayload: string): Promise<string | null> {
  return page.evaluate((skip) => {
    const cells = [...document.querySelectorAll<HTMLElement>(".game .k-hidden")];
    const other = cells.find((cell) => cell.dataset.payload !== skip);
    return other?.dataset.payload ?? null;
  }, notPayload);
}

test("полная партия: раунды, дорога, км, итог", async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  const user = playerId(4, projectIndex(testInfo.project.name), testInfo.repeatEachIndex);
  const screenEl = await startTower(page, user, "Анна", testInfo.project.name);

  await expect(page.locator(".game-tower")).toBeVisible({ timeout: 8000 });
  await expect(screenEl.locator(".road-car")).toBeVisible();
  await expect(screenEl.locator(".road-km")).toContainText("Проехали");

  // фазы короткие: снимаем каждую по факту появления
  const taken = new Set<string>();
  const shootPhase = async (phase: string, name: string) => {
    if (taken.has(phase)) return;
    if (await page.locator(`.game-tower[data-phase="${phase}"]`).isVisible({ timeout: 60 }).catch(() => false)) {
      taken.add(phase);
      await shot(page, testInfo, name);
    }
  };
  for (let i = 0; i < 300; i++) {
    if (await page.getByText(RESULT).isVisible({ timeout: 50 }).catch(() => false)) break;
    await shootPhase("countdown", "01-countdown");
    await shootPhase("preview", "02-preview");
    await shootPhase("input", "03-input");
    const phase = await page.locator(".game-tower").getAttribute("data-phase");
    if (phase === "input") {
      const payload = await hint(user);
      if (payload !== null) {
        await clickCell(page, payload);
        await page.waitForTimeout(100);
        continue;
      }
    }
    await page.waitForTimeout(250);
  }
  await expect(page.getByText(RESULT)).toBeVisible({ timeout: 20_000 });
  await dismissNotices(page);
  await shot(page, testInfo, "04-result");
});

test("ошибка — правильное число в углу, разбор", async ({ page }, testInfo) => {
  test.setTimeout(60_000);
  const user = playerId(5, projectIndex(testInfo.project.name), testInfo.repeatEachIndex);
  const screenEl = await startTower(page, user, "Борис", testInfo.project.name);
  await expect(page.locator('.game-tower[data-phase="input"]')).toBeVisible({ timeout: 8000 });

  const good = await hint(user);
  expect(good).toMatch(/^t:/);
  const bad = await otherHidden(page, good!);
  expect(bad).not.toBeNull();
  await clickCell(page, bad!);   // нажали закрытое число не по порядку

  await expect(page.locator(".game-tower .k-wrong").first()).toBeVisible({ timeout: 5000 });
  await expect(screenEl.locator(".wrong-num").first()).toBeVisible();
  await shot(page, testInfo, "01-review");

  await expect(page.locator('.game-tower[data-phase="input"]')).toBeVisible({ timeout: 15_000 });
  await dismissNotices(page);
  await screenEl.locator('button[data-payload^="q:"]').click();
  await expect(page.getByText(RESULT)).toBeVisible({ timeout: 5000 });
  await shot(page, testInfo, "02-result");
});

test("поле максимального уровня (80) влезает без прокрутки", async ({ page }, testInfo) => {
  const admin = adminId(3, projectIndex(testInfo.project.name), testInfo.repeatEachIndex);
  await openApp(page, admin, "Админ", themeOf(testInfo.project.name));
  const screenEl = mainScreen(page);
  await serverPress(page, admin, "dbg:level:tower:80");
  await screenEl.locator('.tile[data-payload="new:tower"]').click();
  await expect(page.locator(".game-tower")).toBeVisible({ timeout: 5000 });

  const metrics = await page.evaluate(() => ({
    hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    // верхний ряд достижим: при прокрутке в начало он не уходит под край зоны
    topCut: (() => {
      const zone = document.querySelector<HTMLElement>(".game .field-scroll")!;
      zone.scrollTop = 0;
      const cell = document.querySelector<HTMLElement>(".game .gcell")!;
      return zone.getBoundingClientRect().top - cell.getBoundingClientRect().top;
    })(),
    cell: document.querySelector<HTMLElement>(".game-tower .gcell")?.getBoundingClientRect().width ?? 0,
    cells: document.querySelectorAll(".game-tower .gcell").length,
  }));
  expect(metrics.hscroll).toBe(false);
  expect(metrics.topCut).toBeLessThanOrEqual(0);
  expect(metrics.cell).toBeGreaterThanOrEqual(30);
  expect(metrics.cells).toBe(14 * 7);
  await shot(page, testInfo, "01-big-field");
});

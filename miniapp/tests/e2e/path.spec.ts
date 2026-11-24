// Проложи дорогу, e2e (tz-m3 §7.3): показ/ввод/разбор, скрытие препятствий на вводе,
// линия дороги, ошибка, поле 14×7.
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

/** Концы каждой линии дороги лежат внутри клеток поля (SVG-геометрия совпадает с сеткой). */
async function linesInsideCells(page: import("@playwright/test").Page): Promise<boolean> {
  return page.evaluate(() => {
    const svg = document.querySelector<SVGSVGElement>(".game-path .path-lines");
    if (svg === null) return false;
    const box = svg.getBoundingClientRect();
    const [, , vw, vh] = (svg.getAttribute("viewBox") ?? "0 0 0 0").split(" ").map(Number);
    const cells = [...document.querySelectorAll<HTMLElement>(".game-path .gcell")]
      .map((c) => c.getBoundingClientRect());
    const lines = [...svg.querySelectorAll("line")];
    if (lines.length === 0) return false;
    const sx = box.width / vw;
    const sy = box.height / vh;
    const inside = (px: number, py: number) => {
      const x = box.left + px * sx;
      const y = box.top + py * sy;
      return cells.some((r) =>
        x >= r.left + 2 && x <= r.right - 2 && y >= r.top + 2 && y <= r.bottom - 2);
    };
    return lines.every((line) => {
      const x1 = Number(line.getAttribute("x1")), y1 = Number(line.getAttribute("y1"));
      const x2 = Number(line.getAttribute("x2")), y2 = Number(line.getAttribute("y2"));
      return inside(x1, y1) && inside(x2, y2);
    });
  });
}

async function startPath(page: import("@playwright/test").Page, user: number, name: string, projectName: string) {
  await openApp(page, user, name, themeOf(projectName));
  const screenEl = mainScreen(page);
  await screenEl.locator('.tile[data-payload="new:path"]').click();
  await expect(page.locator(".game-path")).toBeVisible({ timeout: 5000 });
  return screenEl;
}

test("полная партия: показ, ввод по линии, дорога готова, итог", async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  const user = playerId(6, projectIndex(testInfo.project.name), testInfo.repeatEachIndex);
  const screenEl = await startPath(page, user, "Анна", testInfo.project.name);

  await expect(page.locator('.game-path[data-phase="preview"]')).toBeVisible({ timeout: 8000 });
  await expect(screenEl.locator(".k-person").first()).toBeVisible();
  await expect(screenEl.locator(".k-house").first()).toBeVisible();
  await expect(screenEl.locator(".k-block").first()).toBeVisible();
  await shot(page, testInfo, "01-preview");

  await expect(page.locator('.game-path[data-phase="input"]')).toBeVisible({ timeout: 5000 });
  await expect(screenEl.locator(".k-block")).toHaveCount(0);   // на вводе поле скрыто
  await shot(page, testInfo, "02-input");

  let doneShot = false;
  for (let i = 0; i < 300; i++) {
    if (await page.getByText(RESULT).isVisible({ timeout: 50 }).catch(() => false)) break;
    if (!doneShot && await page.locator('.game-path[data-phase="done"]').isVisible({ timeout: 50 }).catch(() => false)) {
      await expect(screenEl.locator(".ln-step").first()).toBeAttached();   // у SVG-line пустой bbox — видимостью не проверить
      // линия дороги идёт по клеткам: концы каждого отрезка внутри клеток поля (приёмка M3-1 п. 1)
      expect(await linesInsideCells(page)).toBe(true);
      await shot(page, testInfo, "04-done");
      doneShot = true;
    }
    const phase = await page.locator(".game-path").getAttribute("data-phase");
    if (phase === "input" || phase === "done") {
      const payload = await hint(user);
      if (payload !== null) {
        await clickCell(page, payload);
        if (!doneShot && (await screenEl.locator(".ln-step").count()) > 0) {
          await shot(page, testInfo, "03-road");
        }
        await page.waitForTimeout(100);
        continue;
      }
    }
    await page.waitForTimeout(250);
  }
  await expect(page.getByText(RESULT)).toBeVisible({ timeout: 20_000 });
  await dismissNotices(page);
  await shot(page, testInfo, "05-result");
});

test("ошибка — разбор с кратчайшей дорогой пунктиром", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  // уровень 5+: у кратчайшей дороги несколько промежуточных клеток — пунктир точно есть
  // (на 1-м уровне решение может быть из одних концов — линий не рисуется)
  const admin = adminId(4, projectIndex(testInfo.project.name), testInfo.repeatEachIndex);
  await openApp(page, admin, "Борис", themeOf(testInfo.project.name));
  const screenEl = mainScreen(page);
  await expect(screenEl.locator(".tile").first()).toBeVisible();
  await serverPress(page, admin, "dbg:level:path:5");
  const user = admin;
  await screenEl.locator('.tile[data-payload="new:path"]').click();
  await expect(page.locator('.game-path[data-phase="input"]')).toBeVisible({ timeout: 8000 });

  // на вводе препятствия не видны: ошибка — попасть в ⛔. Валидные пустые клетки
  // просто добавляются в дорогу — перебираем, пока сервер не покажет разбор.
  // Раунд может кончиться доездом до дома: пересобираем клетки каждого нового раунда
  let hitReview = false;
  for (let round = 0; round < 6 && !hitReview; round++) {
    const empties = await page.evaluate(() =>
      [...document.querySelectorAll<HTMLElement>(".game .k-empty")]
        .map((cell) => cell.dataset.payload).filter((p): p is string => p !== undefined));
    for (const payload of empties) {
      if (hitReview) break;
      await clickCell(page, payload);
      hitReview = await page.locator('.game-path[data-phase="review"]').isVisible({ timeout: 900 }).catch(() => false);
    }
    if (!hitReview) {
      // дорога дошла до дома: раунд закрылся сам — дождаться следующего ввода
      await expect(page.locator('.game-path[data-phase="input"]')).toBeVisible({ timeout: 15_000 });
    }
  }
  expect(hitReview).toBe(true);

  // в кадре разбора: ошибка и клетки кратчайшей дороги (пунктир между СОСЕДНИМИ answer —
  // наша тестовая дорога могла разорвать решение, линии необязательны)
  await expect(page.locator(".game-path .k-wrong").first()).toBeAttached();
  await expect(page.locator(".game-path .k-answer").first()).toBeAttached();
  await shot(page, testInfo, "01-review");

  await expect(page.locator('.game-path[data-phase="input"], .game-path[data-phase="countdown"]'))
    .toBeVisible({ timeout: 15_000 });                          // сервер повёл дальше
  await dismissNotices(page);
  await screenEl.locator('button[data-payload^="q:"]').click();
  await expect(page.getByText(RESULT)).toBeVisible({ timeout: 5000 });
  await shot(page, testInfo, "02-result");
});

test("поле максимального уровня 14×7 влезает без прокрутки", async ({ page }, testInfo) => {
  const admin = adminId(5, projectIndex(testInfo.project.name), testInfo.repeatEachIndex);
  await openApp(page, admin, "Админ", themeOf(testInfo.project.name));
  const screenEl = mainScreen(page);
  await serverPress(page, admin, "dbg:level:path:40");
  await screenEl.locator('.tile[data-payload="new:path"]').click();
  await expect(page.locator(".game-path")).toBeVisible({ timeout: 5000 });

  const metrics = await page.evaluate(() => ({
    hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    cell: document.querySelector<HTMLElement>(".game-path .gcell")?.getBoundingClientRect().width ?? 0,
    cells: document.querySelectorAll(".game-path .gcell").length,
  }));
  expect(metrics.hscroll).toBe(false);
  expect(metrics.cell).toBeGreaterThanOrEqual(30);
  expect(metrics.cells).toBe(14 * 7);
  await shot(page, testInfo, "01-big-field");
});

test("размер клетки не меняется между фазами (подсказка фиксированной высоты)", async ({ page }, testInfo) => {
  test.setTimeout(90_000);
  // уровень 20: подсказка показа — 1 строка, подсказка ввода — 3 (изменила бы высоту зоны)
  const admin = adminId(6, projectIndex(testInfo.project.name), testInfo.repeatEachIndex);
  await openApp(page, admin, "Дима", themeOf(testInfo.project.name));
  const screenEl = mainScreen(page);
  await serverPress(page, admin, "dbg:level:path:20");
  await screenEl.locator('.tile[data-payload="new:path"]').click();
  await expect(page.locator('.game-path[data-phase="preview"]')).toBeVisible({ timeout: 8000 });

  const widthAt = () => page.evaluate(
    () => document.querySelector<HTMLElement>(".game-path .gcell")?.getBoundingClientRect().width ?? 0);
  const previewWidth = await widthAt();
  await shot(page, testInfo, "01-preview-45px");

  await expect(page.locator('.game-path[data-phase="input"]')).toBeVisible({ timeout: 8000 });
  const inputWidth = await widthAt();
  await shot(page, testInfo, "02-input-45px");

  expect(inputWidth).toBeCloseTo(previewWidth, 0);   // поле не прыгает между фазами
});

// Матрица памяти, e2e (tz-m3 §7.3): фазы партии, ошибка с разбором, поле 14×7.
// Партия матрицы идёт по часу (60 с) — для полной партии админу укорачиваем её /dbg round 5.
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


async function currentPhase(page: import("@playwright/test").Page): Promise<string | null> {
  const game = page.locator(".game-matrix");
  if (!(await game.isVisible({ timeout: 50 }).catch(() => false))) return null;
  return game.getAttribute("data-phase");
}

test("полная партия по фазам до итога", async ({ page }, testInfo) => {
  test.setTimeout(180_000);
  const admin = adminId(1, projectIndex(testInfo.project.name), testInfo.repeatEachIndex);
  await openApp(page, admin, "Админ", themeOf(testInfo.project.name));
  const screenEl = mainScreen(page);
  await serverPress(page, admin, "dbg:round:15");            // партия матрицы — 15 секунд
  await screenEl.locator('.tile[data-payload="new:matrix"]').click();

  await expect(page.locator(".game-matrix")).toBeVisible({ timeout: 8000 });
  // фазы короткие: снимаем каждую по факту появления, без жёсткого порядка ожиданий
  let quitClicked = false;
  const taken = new Set<string>();
  const shootPhase = async (phase: string, name: string) => {
    if (taken.has(phase)) return;
    if (await page.locator(`.game-matrix[data-phase="${phase}"]`).isVisible({ timeout: 60 }).catch(() => false)) {
      taken.add(phase);
      await shot(page, testInfo, name);
    }
  };
  for (let i = 0; i < 600; i++) {
    if (await page.getByText(RESULT).isVisible({ timeout: 50 }).catch(() => false)) break;
    await shootPhase("countdown", "01-countdown");
    await shootPhase("preview", "02-preview");
    await shootPhase("input", "03-input");
    await shootPhase("done", "04-done");
    const phase = await currentPhase(page);
    if (phase === "input") {
      // время партии вышло: в overtime раунд не кончается сам — «Заканчиваем» как в боте
      if (await screenEl.locator(".gh-right", { hasText: "Время вышло" }).isVisible({ timeout: 50 }).catch(() => false)) {
        await screenEl.locator('button[data-payload^="q:"]').first().click();
        quitClicked = true;
        break;
      }
      const payload = await hint(admin);
      if (payload !== null) {
        await clickCell(page, payload);
        await page.waitForTimeout(100);
        continue;
      }
    }
    await page.waitForTimeout(200);
  }
  // партия в overtime сама не кончается — закрываем, как игрок кнопкой «Закончить»
  // «Закончить» — ровно один раз: если цикл уже нажал, экран сейчас сменится итогом
  // (второе нажатие ловило бы исчезающую кнопку)
  if (!quitClicked && await page.locator(".game-matrix").isVisible({ timeout: 100 }).catch(() => false)) {
    await screenEl.locator('button[data-payload^="q:"]').first().click();
  }
  // итог после конца партии может задержаться на запись результатов — ждём подольше
  await expect(page.getByText(RESULT)).toBeVisible({ timeout: 60_000 });
  await dismissNotices(page);
  await shot(page, testInfo, "05-result");
});

/** Любая клетка вида kind, кроме подсказки — для хода с ошибкой. */
async function otherCellPayload(
  page: import("@playwright/test").Page,
  kind: string,
  notPayload: string,
): Promise<string | null> {
  return page.evaluate(({ kindClass, skip }) => {
    const cells = [...document.querySelectorAll<HTMLElement>(`.game ${kindClass}`)];
    const other = cells.find((cell) => cell.dataset.payload !== skip);
    return other?.dataset.payload ?? null;
  }, { kindClass: `.${kind}`, skip: notPayload });
}

test("ошибка в раунде — разбор с wrong и возврат", async ({ page }, testInfo) => {
  test.setTimeout(60_000);
  const user = playerId(3, projectIndex(testInfo.project.name), testInfo.repeatEachIndex);
  await openApp(page, user, "Борис", themeOf(testInfo.project.name));
  const screenEl = mainScreen(page);
  await screenEl.locator('.tile[data-payload="new:matrix"]').click();
  await expect(page.locator('.game-matrix[data-phase="input"]')).toBeVisible({ timeout: 8000 });

  // среди скрытых клеток есть и другие цели — ошибкой станет только не-цель: перебираем
  const good = await hint(user);
  expect(good).toMatch(/^t:/);
  let missed = false;
  for (let k = 0; k < 20 && !missed; k++) {
    const bad = await otherCellPayload(page, "k-hidden", good!);
    if (bad === null) break;
    await clickCell(page, bad);
    missed = await page.locator(".game-matrix .k-wrong").first().isVisible({ timeout: 800 }).catch(() => false);
  }
  expect(missed).toBe(true);
  await expect(page.locator('.game-matrix[data-phase="review"]')).toBeVisible({ timeout: 5000 });
  await shot(page, testInfo, "01-review");

  await expect(page.locator('.game-matrix[data-phase="input"]')).toBeVisible({ timeout: 15_000 });   // сервер повёл дальше
  await dismissNotices(page);
  await screenEl.locator('button[data-payload^="q:"]').click();
  await expect(page.getByText(RESULT)).toBeVisible({ timeout: 5000 });
  await shot(page, testInfo, "02-result");
});

test("поле максимального уровня 14×7 влезает без прокрутки", async ({ page }, testInfo) => {
  const admin = adminId(2, projectIndex(testInfo.project.name), testInfo.repeatEachIndex);
  await openApp(page, admin, "Админ", themeOf(testInfo.project.name));
  const screenEl = mainScreen(page);
  await serverPress(page, admin, "dbg:level:matrix:40");
  await screenEl.locator('.tile[data-payload="new:matrix"]').click();
  await expect(page.locator(".game-matrix")).toBeVisible({ timeout: 5000 });

  const metrics = await page.evaluate(() => ({
    hscroll: document.documentElement.scrollWidth > document.documentElement.clientWidth,
    // верхний ряд достижим: при прокрутке в начало он не уходит под край зоны
    topCut: (() => {
      const zone = document.querySelector<HTMLElement>(".game .field-scroll")!;
      zone.scrollTop = 0;
      const cell = document.querySelector<HTMLElement>(".game .gcell")!;
      return zone.getBoundingClientRect().top - cell.getBoundingClientRect().top;
    })(),
    cell: document.querySelector<HTMLElement>(".game-matrix .gcell")?.getBoundingClientRect().width ?? 0,
    cells: document.querySelectorAll(".game-matrix .gcell").length,
  }));
  expect(metrics.hscroll).toBe(false);
  expect(metrics.topCut).toBeLessThanOrEqual(0);
  expect(metrics.cell).toBeGreaterThanOrEqual(30);
  expect(metrics.cells).toBe(14 * 7);
  await shot(page, testInfo, "01-big-field");
});

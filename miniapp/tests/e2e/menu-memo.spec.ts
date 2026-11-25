// Сценарий: меню → «Мемо» → ход по подсказке → «Закончить» → итог → «Меню».
import { expect, test } from "@playwright/test";
import { dismissNotices, hint, mainScreen, openApp, shot, themeOf, userId } from "./fake-telegram";

const BASE = 101;   // свой dev_user на «тест + проект» — свои партии и рекорды

test("меню → Мемо → ход → Закончить → итог → Меню", async ({ page }, testInfo) => {
  const user = userId(BASE, testInfo.project.name);
  await openApp(page, user, "Анна", themeOf(testInfo.project.name));
  const screenEl = mainScreen(page);

  // меню: картинка пути сверху, плитки игр
  const tiles = screenEl.locator(".tile");
  await expect(tiles.first()).toBeVisible();
  await expect(screenEl.locator(".image-menu img")).toBeVisible();
  await shot(page, testInfo, "01-menu");

  // партия мемо: экран игры M3 (карты-кнопки с data-payload из шаблона tap)
  // (составной селектор: цепочный .locator ищет потомков, а data-payload — на самой плитке)
  await screenEl.locator('.tile[data-payload="new:memo"]').click();
  await expect(page.locator('.game-memo[data-phase="play"]')).toBeVisible();
  await shot(page, testInfo, "02-memo-board");

  // ход по подсказке сервера: кнопка с таким data-payload
  const payload = await hint(user);
  expect(payload).toMatch(/^t:/);
  await screenEl.locator(`button[data-payload="${payload}"]`).click();
  await shot(page, testInfo, "03-memo-move");

  // записанная партия может принести карточки (итоги недели и т.п.) — закрыть
  await dismissNotices(page);

  // закончить партию — итог, затем меню
  await screenEl.locator('button[data-payload^="q:"]').click();
  await expect(screenEl.getByText("Партия окончена")).toBeVisible();
  await expect(screenEl.locator("button.btn.primary").first()).toBeVisible();   // «Ещё раз»
  await shot(page, testInfo, "04-result");
  await dismissNotices(page);
  await screenEl.locator('button[data-payload="menu"]').click();
  await expect(tiles.first()).toBeVisible();
  await shot(page, testInfo, "05-menu-again");
});

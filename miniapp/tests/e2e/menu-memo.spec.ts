// Сценарий: меню → «Мемо» → ход по подсказке → «Закончить» → итог → «Меню».
import { expect, test } from "@playwright/test";
import { hint, openApp, shot, themeOf } from "./fake-telegram";

const USER = 101;   // свой dev_user — свои партии и рекорды, тесты не мешают друг другу

test("меню → Мемо → ход → Закончить → итог → Меню", async ({ page }, testInfo) => {
  await openApp(page, USER, "Анна", themeOf(testInfo.project.name));

  // меню: картинка пути сверху, плитки игр
  const tiles = page.locator(".tile");
  await expect(tiles.first()).toBeVisible();
  await expect(page.locator(".image-menu img")).toBeVisible();
  await shot(page, testInfo, "01-menu");

  // партия мемо: пока без компонента игры — заглушка с универсальным рендером
  await page.locator('.tile[data-payload="new:memo"]').click();
  await expect(page.locator(".cell").first()).toBeVisible();
  await expect(page.locator(".soon")).toBeVisible();
  await shot(page, testInfo, "02-memo-board");

  // ход по подсказке сервера: кнопка с таким data-payload
  const payload = await hint(USER);
  expect(payload).toMatch(/^t:/);
  await page.locator(`button[data-payload="${payload}"]`).click();
  await shot(page, testInfo, "03-memo-move");

  // закончить партию — итог, затем меню
  await page.locator('button[data-payload^="q:"]').click();
  await expect(page.getByText("Партия окончена")).toBeVisible();
  await shot(page, testInfo, "04-result");
  await page.locator('button[data-payload="menu"]').click();
  await expect(tiles.first()).toBeVisible();
  await shot(page, testInfo, "05-menu-again");
});

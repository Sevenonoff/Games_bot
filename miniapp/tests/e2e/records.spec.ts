// Сценарий: меню → «Рекорды» → «Мемо» → «Меню».
import { expect, test } from "@playwright/test";
import { dismissNotices, mainScreen, openApp, shot, themeOf, userId } from "./fake-telegram";

const BASE = 111;

test("меню → Рекорды → Мемо → Меню", async ({ page }, testInfo) => {
  const user = userId(BASE, testInfo.project.name);
  await openApp(page, user, "Борис", themeOf(testInfo.project.name));
  const screenEl = mainScreen(page);

  await dismissNotices(page);
  await screenEl.locator('button[data-payload="rec"]').click();
  const gameRow = screenEl.locator('button[data-payload="rec:memo"]');
  await expect(gameRow).toBeVisible();          // список игр в рекордах
  await shot(page, testInfo, "01-records-menu");

  await gameRow.click();
  await expect(screenEl.getByText("🃏 Мемо")).toBeVisible();          // таблица рекордов мемо
  await expect(screenEl.locator('button[data-payload="new:memo"]')).toBeVisible();   // «▶️ Играть»
  await expect(screenEl.locator('button[data-payload="new:memo"]').first()).toHaveClass(/primary/);
  await shot(page, testInfo, "02-records-memo");

  await dismissNotices(page);
  await screenEl.locator('button[data-payload="menu"]').click();
  await expect(screenEl.locator(".tile").first()).toBeVisible();
  await shot(page, testInfo, "03-menu-again");
});

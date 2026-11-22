// Сценарий: меню → «Рекорды» → «Мемо» → «Меню».
import { expect, test } from "@playwright/test";
import { openApp, shot, themeOf } from "./fake-telegram";

const USER = 102;

test("меню → Рекорды → Мемо → Меню", async ({ page }, testInfo) => {
  await openApp(page, USER, "Борис", themeOf(testInfo.project.name));

  await page.locator('button[data-payload="rec"]').click();
  const gameRow = page.locator('button[data-payload="rec:memo"]');
  await expect(gameRow).toBeVisible();          // список игр в рекордах
  await shot(page, testInfo, "01-records-menu");

  await gameRow.click();
  await expect(page.getByText("🃏 Мемо")).toBeVisible();          // таблица рекордов мемо
  await expect(page.locator('button[data-payload="new:memo"]')).toBeVisible();   // «▶️ Играть»
  await shot(page, testInfo, "02-records-memo");

  await page.locator('button[data-payload="menu"]').click();
  await expect(page.locator(".tile").first()).toBeVisible();
  await shot(page, testInfo, "03-menu-again");
});

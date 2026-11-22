// Сценарий: «Мои друзья» и «Настройки» открываются и возвращаются в меню.
import { expect, test } from "@playwright/test";
import { openApp, shot, themeOf } from "./fake-telegram";

const USER = 103;

test("друзья и настройки открываются и возвращаются", async ({ page }, testInfo) => {
  await openApp(page, USER, "Вера", themeOf(testInfo.project.name));
  const tiles = page.locator(".tile");
  await expect(tiles.first()).toBeVisible();

  // друзья
  await page.locator('button[data-payload="fr"]').click();
  await expect(page.getByText("Мои друзья")).toBeVisible();
  await expect(page.getByText("Пока нет друзей", { exact: false })).toBeVisible();
  await shot(page, testInfo, "01-friends");
  await page.locator('button[data-payload="menu"]').click();
  await expect(tiles.first()).toBeVisible();

  // настройки
  await page.locator('button[data-payload="set"]').click();
  await expect(page.getByText("Настройки")).toBeVisible();
  await shot(page, testInfo, "02-settings");

  // переключение настройки работает и возвращается
  await page.locator('button[data-payload="set:fn"]').click();
  await expect(page.getByText("Настройки")).toBeVisible();
  await shot(page, testInfo, "03-settings-toggled");
  await page.locator('button[data-payload="menu"]').click();
  await expect(tiles.first()).toBeVisible();
  await shot(page, testInfo, "04-menu-again");
});

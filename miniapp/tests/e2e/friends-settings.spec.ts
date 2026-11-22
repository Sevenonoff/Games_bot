// Сценарий: «Мои друзья» и «Настройки» открываются и возвращаются в меню.
import { expect, test } from "@playwright/test";
import { dismissNotices, mainScreen, openApp, shot, themeOf, userId } from "./fake-telegram";

const BASE = 121;

test("друзья и настройки открываются и возвращаются", async ({ page }, testInfo) => {
  const user = userId(BASE, testInfo.project.name);
  await openApp(page, user, "Вера", themeOf(testInfo.project.name));
  const screenEl = mainScreen(page);
  const tiles = screenEl.locator(".tile");
  await expect(tiles.first()).toBeVisible();

  // друзья
  await dismissNotices(page);
  await screenEl.locator('button[data-payload="fr"]').click();
  await expect(screenEl.getByText("Мои друзья")).toBeVisible();
  await expect(screenEl.getByText("Пока нет друзей", { exact: false })).toBeVisible();
  await shot(page, testInfo, "01-friends");
  await dismissNotices(page);
  await screenEl.locator('button[data-payload="menu"]').click();
  await expect(tiles.first()).toBeVisible();

  // настройки
  await dismissNotices(page);
  await screenEl.locator('button[data-payload="set"]').click();
  await expect(screenEl.getByText("Настройки")).toBeVisible();
  await shot(page, testInfo, "02-settings");

  // переключение настройки работает и возвращается
  await screenEl.locator('button[data-payload="set:fn"]').click();
  await expect(screenEl.getByText("Настройки")).toBeVisible();
  await shot(page, testInfo, "03-settings-toggled");
  await dismissNotices(page);
  await screenEl.locator('button[data-payload="menu"]').click();
  await expect(tiles.first()).toBeVisible();
  await shot(page, testInfo, "04-menu-again");
});

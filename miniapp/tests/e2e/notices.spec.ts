// Карточки notice: админ шлёт press("dbg:notify") вторым соединением — бот присылает
// уведомление друзей, напоминание и итоги недели. Карточки идут очередью, кнопка
// карточки работает, крестик закрывает. Админ у каждого проекта свой (DEV_ADMINS=1..4).
import { expect, test } from "@playwright/test";
import { mainScreen, openApp, projectIndex, shot, themeOf } from "./fake-telegram";

const ADMIN_BASE = 1;   // DEV_ADMINS="1 2 3 4" — id 1 + номер проекта

/** Второе соединение того же игрока: hello и press("dbg:notify") ровно один раз, ждём три карточки. */
async function pressDebugNotify(page: import("@playwright/test").Page, admin: number): Promise<void> {
  await page.evaluate((id: number) => new Promise<void>((resolve, reject) => {
    const ws = new WebSocket(`ws://${location.host}/ws`);
    let notices = 0;
    let pressed = false;   // ответ на dbg:notify — тоже screen: жмём только по первому кадру
    const fail = setTimeout(() => reject(new Error("нет трёх карточек за 5 с")), 5000);
    ws.onopen = () => {
      ws.send(JSON.stringify({ type: "hello", dev_user: { id, name: "Админ" }, client: "e2e" }));
    };
    ws.onmessage = (ev: MessageEvent) => {
      const msg = JSON.parse(String(ev.data)) as { type: string };
      if (msg.type === "screen" && !pressed) {
        pressed = true;
        ws.send(JSON.stringify({ type: "press", payload: "dbg:notify", seq: 1 }));
      }
      if (msg.type === "notice") {
        notices += 1;
        if (notices === 3) {
          clearTimeout(fail);
          ws.close();
          resolve();
        }
      }
    };
    ws.onerror = () => reject(new Error("ws error"));
  }), admin);
}

test("карточки уведомлений идут очередью", async ({ page }, testInfo) => {
  const admin = ADMIN_BASE + projectIndex(testInfo.project.name);
  await openApp(page, admin, "Админ", themeOf(testInfo.project.name));
  await expect(mainScreen(page).locator(".tile").first()).toBeVisible();

  await pressDebugNotify(page, admin);

  // первая карточка: уведомление от друзей
  const sheet = page.locator(".notice-sheet");
  await expect(sheet).toBeVisible();
  await expect(sheet.getByText("тренировались", { exact: false })).toBeVisible();
  await shot(page, testInfo, "01-notice-friends");

  // кнопка карточки: шлёт press и закрывает её, открывается следующая (напоминание)
  await sheet.locator('button[data-payload="fr"]').click();
  await expect(sheet.getByText("Время тренировки", { exact: false })).toBeVisible();
  await shot(page, testInfo, "02-notice-reminder");

  // крестик закрывает, очередь показывает итоги недели
  await sheet.locator(".notice-close").click();
  await expect(sheet.getByText("Итоги недели")).toBeVisible();
  await shot(page, testInfo, "03-notice-weekly");

  await sheet.locator(".notice-close").click();
  await expect(sheet).toHaveCount(0);
  await shot(page, testInfo, "04-notice-done");
});

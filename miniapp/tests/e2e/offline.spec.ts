// Разрыв соединения: полоса «Нет связи…» появляется через секунду, после восстановления —
// hello без start, сервер возвращает меню.
//
// Установленный WebSocket на localhost Chromium в offline не рвёт (проверено), поэтому
// разрыв делаем перехватом routeWebSocket: close() по команде и отказ новым соединениям,
// пока сеть «отключена». setOffline оставлен как в ТЗ — он честно рвёт всё остальное.
import { expect, test } from "@playwright/test";
import type { WebSocketRoute } from "@playwright/test";
import { openApp, shot, themeOf } from "./fake-telegram";

const USER = 105;

test("разрыв связи — полоса, восстановление — меню", async ({ page }, testInfo) => {
  const sockets: WebSocketRoute[] = [];
  let broken = false;                 // true — сеть «отключена»: новые соединения не проходят
  await page.routeWebSocket(/\/ws$/, (ws) => {
    if (broken) {
      ws.close();
      return;
    }
    sockets.push(ws);
    ws.connectToServer();
  });

  await openApp(page, USER, "Гоша", themeOf(testInfo.project.name));
  const tiles = page.locator(".tile");
  await expect(tiles.first()).toBeVisible();

  // уходим с меню, чтобы после восстановления увидеть именно новый экран
  await page.locator('button[data-payload="rec"]').click();
  await expect(page.locator('button[data-payload="rec:memo"]')).toBeVisible();

  // разрыв: полоса появляется через ~1 с
  broken = true;
  await page.context().setOffline(true);
  await sockets[0]!.close();
  await expect(page.locator(".offline-bar")).toBeVisible({ timeout: 6000 });
  await expect(page.locator(".offline-bar")).toHaveText("Нет связи…");
  await shot(page, testInfo, "01-offline");

  // восстановление: переподключение и hello без start → меню
  await page.context().setOffline(false);
  broken = false;
  await expect(page.locator(".offline-bar")).toHaveCount(0, { timeout: 10_000 });
  await expect(tiles.first()).toBeVisible({ timeout: 10_000 });
  await shot(page, testInfo, "02-reconnected");
});

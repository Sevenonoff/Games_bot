import { chromium } from "@playwright/test";
const USER = 490;
const browser = await chromium.launch();
const page = await browser.newPage({ viewport: { width: 360, height: 640 } });
await page.route(/telegram-web-app\.js$/, (r) => r.fulfill({ status: 200, body: "" }));
await page.addInitScript(() => {
  window.Telegram = { WebApp: { initData: "", initDataUnsafe: {}, themeParams: {}, ready() {}, expand() {}, onEvent() {}, BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} }, HapticFeedback: { selectionChanged() {}, notificationOccurred() {}, impactOccurred() {} }, showConfirm: (t, cb) => { console.log("CONFIRM:", t); cb?.(true); }, openTelegramLink() {} } };
});
await page.goto(`http://127.0.0.1:8449/app/?dev_user=${USER}&dev_name=Probe`);
await page.waitForSelector(".tile");
const click = async (payload) => {
  await page.locator(`.app > * button[data-payload="${payload}"]`).first().click();
  await page.waitForTimeout(300);
};
await click("sea");
await click("ai");
await click("ain:normal");
await click("ain:normal:0");
await click("ain:normal:0:reduced");
await click("ain:normal:0:reduced:auto");
await page.waitForSelector('.game-sea[data-status="active"]', { timeout: 8000 });
console.log("battle active");
const hint = () => fetch(`http://127.0.0.1:8449/dev/hint?user=${USER}`).then((r) => r.json()).then((d) => d.payload);
for (let i = 0; i < 3; i++) {
  const h = await hint();
  if (h === null) { await page.waitForTimeout(400); continue; }
  await page.locator(`button[data-payload="${h}"]`).first().click();
  await page.waitForSelector('.game-sea[data-turn="me"]', { timeout: 15000 });
}
console.log("after 3 shots");
console.log("surrender visible:", await page.locator('button[data-payload^="mpg:"]').count());
await page.locator('button[data-payload^="mpg:"]').click();
await page.waitForTimeout(2000);
console.log("surrender clicked; result:", await page.getByText("Партия окончена").isVisible().catch(() => false));
console.log("app text:", (await page.locator(".app").textContent())?.slice(0, 200));
await page.screenshot({ path: "/tmp/sea-after.png", fullPage: true });
await browser.close();

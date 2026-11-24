// Подложка Telegram для e2e: скрипт telegram-web-app.js не грузится с telegram.org
// (route → пустой ответ), вместо него window.Telegram.WebApp с initData: "",
// themeParams выбранной темы и счётчиками вызовов для проверок (window.__tg.calls).
//
// Изоляция прогонов (tz-m2 §5.3, приёмка M2-1): проекты идут параллельно, а у игрока
// одна открытая партия и общие уведомления — поэтому id игрока уникален для пары
// «тест + проект»: базовый id теста + номер проекта (0…3).
import type { Locator, Page, TestInfo } from "@playwright/test";

export type Theme = "light" | "dark";

export const PROJECTS = [
  { name: "chromium-light-360", viewport: { width: 360, height: 640 } },
  { name: "chromium-light-414", viewport: { width: 414, height: 896 } },
  { name: "chromium-dark-360", viewport: { width: 360, height: 640 } },
  { name: "chromium-dark-414", viewport: { width: 414, height: 896 } },
];

const THEME_PARAMS: Record<Theme, Record<string, string>> = {
  light: {
    bg_color: "#ffffff",
    text_color: "#000000",
    hint_color: "#999999",
    link_color: "#2481cc",
    button_color: "#2481cc",
    button_text_color: "#ffffff",
    secondary_bg_color: "#efeff4",
  },
  dark: {
    bg_color: "#17212b",
    text_color: "#ffffff",
    hint_color: "#aaaaaa",
    link_color: "#8774e1",
    button_color: "#5288c1",
    button_text_color: "#ffffff",
    secondary_bg_color: "#232e3c",
  },
};

/** Тема проекта: по слову dark/light в его имени. */
export function themeOf(projectName: string): Theme {
  return projectName.includes("dark") ? "dark" : "light";
}

/** Номер проекта в PROJECTS (0…3). */
export function projectIndex(projectName: string): number {
  return PROJECTS.findIndex((p) => p.name === projectName);
}

/** dev_user теста: базовый id теста + номер проекта — у каждого окна свой игрок. */
export function userId(base: number, projectName: string): number {
  return base + projectIndex(projectName);
}

type TgCalls = {
  ready: number;
  expand: number;
  backShow: number;
  backHide: number;
  selection: number;
  haptics: string[];
  confirms: string[];
  links: string[];
};

function injectTelegram(arg: { theme: Record<string, string> }): void {
  const calls: TgCalls = { ready: 0, expand: 0, backShow: 0, backHide: 0, selection: 0, haptics: [],
                          confirms: [], links: [] };
  const backHandlers: Array<() => void> = [];
  window.Telegram = {
    WebApp: {
      initData: "",
      initDataUnsafe: {},
      themeParams: arg.theme,
      ready: () => { calls.ready += 1; },
      expand: () => { calls.expand += 1; },
      onEvent: () => {},
      BackButton: {
        show: () => { calls.backShow += 1; },
        hide: () => { calls.backHide += 1; },
        onClick: (cb: () => void) => { backHandlers.push(cb); },
        offClick: (cb: () => void) => {
          const i = backHandlers.indexOf(cb);
          if (i >= 0) backHandlers.splice(i, 1);
        },
      },
      HapticFeedback: {
        selectionChanged: () => { calls.selection += 1; },
        notificationOccurred: (type: string) => { calls.haptics.push(`notify:${type}`); },
        impactOccurred: (style: string) => { calls.haptics.push(`impact:${style}`); },
      },
      // диалог подтверждения: в тестах всегда «ОК», текст запоминается
      showConfirm: (message: string, callback?: (ok: boolean) => void) => {
        calls.confirms.push(message);
        callback?.(true);
      },
      openTelegramLink: (url: string) => { calls.links.push(url); },
    },
  };
  window.__tg = { calls, backHandlers };
}

declare global {
  interface Window {
    __tg?: { calls: TgCalls; backHandlers: Array<() => void> };
  }
}

export const APP_ORIGIN = `http://127.0.0.1:${process.env.E2E_PORT ?? "8448"}`;

/** Открывает приложение с dev-входом: ?dev_user=<id>&dev_name=<имя>. */
export async function openApp(page: Page, user: number, name: string, theme: Theme): Promise<void> {
  await page.route(/telegram-web-app\.js$/, (route) =>
    route.fulfill({ status: 200, contentType: "application/javascript", body: "" }));
  await page.addInitScript(injectTelegram, { theme: THEME_PARAMS[theme] });
  const url = new URL("/app/", APP_ORIGIN);
  url.searchParams.set("dev_user", String(user));
  url.searchParams.set("dev_name", name);
  await page.goto(url.toString());
}

/** Основной экран (не карточки notice): кнопки ищем внутри него — сервер вправе
 *  прислать карточку в любой момент, и её кнопки не должны путаться с экраном.
 *  Корень экрана игры (M3/M4) — элемент с классом game прямо в .app. */
export function mainScreen(page: Page): Locator {
  return page.locator(".app > .screen, .app > .placeholder, .app > .game");
}

/** Закрыть карточки-уведомления, если сервер их прислал (итоги недели и т.п.). */
export async function dismissNotices(page: Page): Promise<void> {
  const close = page.locator(".notice-sheet .notice-close");
  for (let i = 0; i < 10 && (await close.count()) > 0; i++) {
    await close.first().click();
  }
}

/** Нажатие от имени игрока вторым соединением, мимо экрана: например, отладочная команда
 *  админа `dbg:level:matrix:40` (id из DEV_ADMINS). Ждёт ответ сервера на это нажатие.
 *  Экран в окне приложения при этом не меняется — следующее нажатие в окне берёт новое состояние.
 *  Вызывать до начала партии: hello второго соединения открывает меню, а уход в меню закрывает партию уровня. */
export async function serverPress(page: Page, user: number, payload: string): Promise<void> {
  await page.evaluate(({ id, data }) => new Promise<void>((resolve, reject) => {
    const ws = new WebSocket(`ws://${location.host}/ws`);
    let pressed = false;
    const fail = setTimeout(() => reject(new Error(`нет ответа на ${data} за 5 с`)), 5000);
    ws.onopen = () => ws.send(JSON.stringify({ type: "hello", dev_user: { id, name: "Тест" }, client: "e2e" }));
    ws.onmessage = (ev: MessageEvent) => {
      const msg = JSON.parse(String(ev.data)) as { type: string; seq?: number | null };
      if (msg.type === "error") reject(new Error(`ошибка сервера на ${data}`));
      if (msg.type !== "screen") return;
      if (!pressed) {                       // первый кадр — меню после hello
        pressed = true;
        ws.send(JSON.stringify({ type: "press", payload: data, seq: 1 }));
      } else if (msg.seq === 1) {
        clearTimeout(fail);
        ws.close();
        resolve();
      }
    };
    ws.onerror = () => reject(new Error("ws error"));
  }), { id: user, data: payload });
}

/** Верный ход игрока по подсказке dev-сервера (tz-m1 §2.6). */
export async function hint(user: number): Promise<string | null> {
  const res = await fetch(`${APP_ORIGIN}/dev/hint?user=${user}`);
  if (!res.ok) throw new Error(`hint ${user}: HTTP ${res.status}`);
  const data = await res.json() as { payload: string | null };
  return data.payload;
}

/** Скриншот шага в tests/e2e/__screenshots__/ (Playwright сам создаст папку; в git не кладутся).
 *  Имя: <проект>-<spec-файл>-<шаг>.png — одинаковые шаги разных игр («01-review») не затирают
 *  друг друга. При повторах (--repeat-each) снимок последнего повтора перезаписывает прежние. */
export async function shot(page: Page, testInfo: TestInfo, name: string): Promise<void> {
  const dir = new URL("./__screenshots__/", import.meta.url).pathname;
  const spec = (testInfo.file.split(/[\\/]/).pop() ?? "").replace(/\.spec\.ts$/, "");
  await page.screenshot({ path: `${dir}${testInfo.project.name}-${spec}-${name}.png` });
}

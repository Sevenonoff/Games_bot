// themeParams Telegram → CSS-переменные (tz-m2 §3.6). Значения по умолчанию (светлая
// тема) заданы в app.css на :root — недостающие параметры их не перетирают.
import type { TelegramWebApp, TgThemeParams } from "../telegram";

const VARS: Array<[keyof TgThemeParams, string]> = [
  ["bg_color", "--bg"],
  ["text_color", "--text"],
  ["hint_color", "--hint"],
  ["link_color", "--link"],
  ["button_color", "--button"],
  ["button_text_color", "--button-text"],
  ["secondary_bg_color", "--secondary-bg"],
];

export function applyTheme(params: TgThemeParams): void {
  for (const [name, cssVar] of VARS) {
    const value = params[name];
    if (value) document.documentElement.style.setProperty(cssVar, value);
  }
}

/** Подписка на смену темы (тёмная/светлая в настройках Telegram). */
export function watchTheme(tg: TelegramWebApp): void {
  tg.onEvent("themeChanged", () => applyTheme(tg.themeParams));
}

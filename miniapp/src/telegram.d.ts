// Нужное подмножество window.Telegram.WebApp (полный SDK — тег telegram-web-app.js в index.html).
// Объекта может не быть: страница открыта не в Telegram — весь код это переживает.

export interface TgThemeParams {
  bg_color?: string;
  text_color?: string;
  hint_color?: string;
  link_color?: string;
  button_color?: string;
  button_text_color?: string;
  secondary_bg_color?: string;
}

export interface TgHapticFeedback {
  selectionChanged(): void;
  notificationOccurred(type: "error" | "success" | "warning"): void;
  impactOccurred(style: "light" | "medium" | "heavy" | "rigid" | "soft"): void;
}

export interface TgBackButton {
  show(): void;
  hide(): void;
  onClick(callback: () => void): void;
  offClick(callback: () => void): void;
}

export interface TelegramWebApp {
  initData: string;
  initDataUnsafe: { start_param?: string };
  ready(): void;
  expand(): void;
  themeParams: TgThemeParams;
  onEvent(event: "themeChanged", listener: () => void): void;
  HapticFeedback: TgHapticFeedback;
  BackButton: TgBackButton;
  /** Системный диалог «ОК / Отмена» (M4: подтверждение сдачи). */
  showConfirm(message: string, callback?: (ok: boolean) => void): void;
  /** Открыть ссылку t.me внутри Telegram (M4: «Отправить другу»). */
  openTelegramLink(url: string): void;
}

declare global {
  interface Window {
    Telegram?: { WebApp: TelegramWebApp };
  }
}

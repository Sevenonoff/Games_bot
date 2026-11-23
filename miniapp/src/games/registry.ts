// Точка подключения игр (tz-m2 §3.7): kind → компонент. M3 и M4 только добавляют
// сюда строки; каркас и игры больше ничем не связаны.
import type { ComponentType } from "preact";
import type { Screen, View } from "../protocol";
import type { TelegramWebApp } from "../telegram";

export type GameProps<V> = {
  view: V;
  screen: Screen;
  press: (payload: string) => void;
  note: string | null;
  tg: TelegramWebApp | null;   // SDK Telegram (вибрация, диалоги); null — страница открыта не в Telegram
};

export const games: Partial<Record<View["kind"], ComponentType<GameProps<any>>>> = {};

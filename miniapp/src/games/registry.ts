// Точка подключения игр (tz-m2 §3.7): kind → компонент. M3 и M4 только добавляют
// сюда строки; каркас и игры больше ничем не связаны.
import type { ComponentType } from "preact";
import type { Screen, View } from "../protocol";
import type { TelegramWebApp } from "../telegram";
import { Memo } from "./memo/Memo";
import { Matrix } from "./matrix/Matrix";
import { Tower } from "./tower/Tower";
import { Path } from "./path/Path";
import { Sea } from "./sea/Sea";

export type GameProps<V> = {
  view: V;
  screen: Screen;
  press: (payload: string) => void;
  note: string | null;
  tg: TelegramWebApp | null;   // SDK Telegram (вибрация, диалоги); null — страница открыта не в Telegram
};

export const games: Partial<Record<View["kind"], ComponentType<GameProps<any>>>> = {
  memo: Memo,
  matrix: Matrix,
  tower: Tower,
  path: Path,
  sea: Sea,
};

// Типы протокола WebSocket и view — ровно по контракту docs/miniapp/README.md §4
// и docs/miniapp/tz-m1-core.md §3. Файл правится только по ТЗ.

// --- экраны ---

export interface Button {
  text: string;
  data: string;           // payload, который уходит на сервер при нажатии
}

export interface Screen {
  text: string;           // HTML-подмножество Telegram (см. app/html.ts)
  rows: Button[][];       // ряды кнопок, как в клавиатуре бота
  image: string | null;   // URL картинки (путь, открытка), без базы
  view: View | null;      // структурное состояние партии; null — универсальный рендер
}

// --- view игр (общая часть у всех kind) ---

export type ViewKind = "memo" | "matrix" | "tower" | "path" | "sea";

/** Шаблоны payload'ов; клиент подставляет {r}, {c}, {o} и никогда не собирает payload сам. */
export type Actions = Record<string, string>;

export type Phase = "countdown" | "preview" | "input" | "review" | "done";

export interface Grid<C> {
  rows: number;
  cols: number;
  cells: C[][];
}

/** Ячейка поля: k — вид, v — необязательный текст (эмодзи, число). */
export type MatrixCell =
  | { k: "hidden" } | { k: "shown" } | { k: "answer" } | { k: "wrong" };
export type TowerCell =
  | { k: "inactive" } | { k: "hidden" } | { k: "number"; v: string }
  | { k: "wrong"; v?: string };
export type PathCell =
  | { k: "empty" } | { k: "block" } | { k: "step" } | { k: "answer" }
  | { k: "wrong" } | { k: "person"; v: string } | { k: "house"; v: string };
export type MemoCell =
  | { k: "back" } | { k: "face"; v: string } | { k: "matched"; v: string };
export type SeaCell =
  | { k: "sea" } | { k: "ship" } | { k: "hit" } | { k: "sunk" } | { k: "miss" };

export interface MemoView {
  kind: "memo";
  title: string;
  level: number;
  score: number;
  combo: string;
  actions: Actions;
  done: boolean;
  hint?: string;
  pairs: { found: number; total: number };
  moves: { made: number; limit: number };
  grid: Grid<MemoCell>;
}

export interface MatrixView {
  kind: "matrix";
  title: string;
  level: number;
  score: number;
  combo: string;
  actions: Actions;
  phase: Phase;
  countdown?: number;
  hint?: string;
  timer: { left: number; total: number; overtime: boolean };  // только у матрицы
  grid: Grid<MatrixCell>;
}

export interface TowerView {
  kind: "tower";
  title: string;
  level: number;
  score: number;
  combo: string;
  actions: Actions;
  phase: Phase;
  countdown?: number;
  hint?: string;
  rounds?: { current: number; total: number };   // поездка и дорога
  extra: { road: number; km: number };            // доля пути 0..1 и проехано км
  grid: Grid<TowerCell>;
}

export interface PathView {
  kind: "path";
  title: string;
  level: number;
  score: number;
  combo: string;
  actions: Actions;
  phase: Phase;
  countdown?: number;
  hint?: string;
  rounds?: { current: number; total: number };
  grid: Grid<PathCell>;
}

export interface SeaView {
  kind: "sea";
  title: string;
  score: number;
  actions: Actions;
  code: string;
  opponent: { name: string; ai: boolean };
  set: "full" | "reduced";
  status: "placing" | "waiting_ready" | "active" | "finished" | "waiting";
  turn: "me" | "them" | null;
  thinking: boolean;
  timer: { left: number; total: number } | null;
  timeouts: { me: number; them: number; max: number };
  last: { by: "me" | "them"; result: "miss" | "hit" | "sunk" }[];
  own: Grid<SeaCell>;
  enemy: Grid<SeaCell>;
  blink: { board: "own" | "enemy"; cells: [number, number][]; frame: "hit" | "sunk" } | null;
  result: {
    won: boolean;
    reason: "sunk" | "timeouts" | "surrender";
    score: number;
    rating: number;
    delta: number;
    journey: string[];
  } | null;
  placement: {
    sizes: number[];
    fixed: [number, number][][];
    current: [number, number][];
    forbidden: [number, number][];
    left: number;
  } | null;
  invite: { link: string; code: string } | null;   // status == "waiting"
}

export type View = MemoView | MatrixView | TowerView | PathView | SeaView;

// --- сообщения ---

export const CLIENT_VERSION = "1.0.0";

export interface HelloMessage {
  type: "hello";
  client: string;
  initData?: string;                        // подпись Telegram; пустая — не задана
  dev_user?: { id: number; name: string };  // вход без Telegram (dev-режим сервера)
  start?: string;                           // параметр ссылки (?startapp=… / ?start=…)
}

export interface PressMessage {
  type: "press";
  payload: string;
  seq: number;
}

export type ClientMessage = HelloMessage | PressMessage;

export interface ScreenFrame {
  type: "screen";
  seq: number | null;      // ответ на press несёт его seq; правка по таймеру — null
  note: string | null;     // всплывающее уведомление
  screen: Screen | null;   // null — экран не меняется, только note
}

export interface NoticeFrame {
  type: "notice";          // бот «сам пишет»: карточка поверх экрана
  screen: Screen;
}

export interface ErrorFrame {
  type: "error";
  code: "auth" | "bad_request" | "server";
  message?: string;
  seq?: number | null;
}

export type ServerMessage = ScreenFrame | NoticeFrame | ErrorFrame;

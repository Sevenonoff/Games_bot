// App: подключение (подменяем Connection), toast note с вибрацией, индикатор связи,
// карточки notice очередью, BackButton на не-меню, экран auth, press с selectionChanged.
import { act, cleanup, fireEvent, render } from "@testing-library/preact";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { App } from "../../src/app/App";
import type { ConnectionCallbacks } from "../../src/connection";
import { Connection } from "../../src/connection";
import type { Screen, View } from "../../src/protocol";
import type { TelegramWebApp } from "../../src/telegram";

/** Подделка сокета (как в connection.test.ts). */
class FakeSocket {
  static created: FakeSocket[] = [];
  sent: string[] = [];
  readyState = 0;
  closed = false;
  onopen: (() => void) | null = null;
  onclose: (() => void) | null = null;
  onerror: (() => void) | null = null;
  onmessage: ((event: { data: string }) => void) | null = null;

  constructor() {
    FakeSocket.created.push(this);
  }

  send(data: string): void {
    this.sent.push(data);
  }

  close(): void {
    if (this.closed) {
      return;
    }
    this.closed = true;
    this.readyState = 3;
    this.onclose?.();
  }

  open(): void {
    this.readyState = 1;
    this.onopen?.();
  }

  drop(): void {
    this.readyState = 3;
    this.onclose?.();
  }

  message(obj: unknown): void {
    this.onmessage?.({ data: JSON.stringify(obj) });
  }
}

/** Подделка Telegram.WebApp со счётчиками вызовов. */
function fakeTelegram() {
  const calls = { ready: 0, expand: 0, backShow: 0, backHide: 0, selection: 0 };
  const haptics: string[] = [];
  const backHandlers: Array<() => void> = [];
  const tg: TelegramWebApp = {
    initData: "",
    initDataUnsafe: {},
    ready: () => { calls.ready += 1; },
    expand: () => { calls.expand += 1; },
    themeParams: {},
    onEvent: () => {},
    BackButton: {
      show: () => { calls.backShow += 1; },
      hide: () => { calls.backHide += 1; },
      onClick: (cb) => { backHandlers.push(cb); },
      offClick: (cb) => {
        const i = backHandlers.indexOf(cb);
        if (i >= 0) backHandlers.splice(i, 1);
      },
    },
    HapticFeedback: {
      selectionChanged: () => { calls.selection += 1; },
      notificationOccurred: (type) => { haptics.push(`notify:${type}`); },
      impactOccurred: (style) => { haptics.push(`impact:${style}`); },
    },
    showConfirm: (_message, callback) => { callback?.(true); },
    openTelegramLink: () => {},
  };
  return { tg, calls, haptics, backHandlers };
}

const screen = (over: Partial<Screen> = {}): Screen => ({
  text: "текст",
  rows: [],
  image: null,
  view: null,
  ...over,
});

// меню — по обеим кнопкам new:memo и sea (tz-m2 §3.5, приёмка M2-1)
const menuScreen = screen({
  text: "🎮 Игры",
  rows: [
    [{ text: "🃏 Мемо", data: "new:memo" }],
    [{ text: "🚢 Морской бой", data: "sea" }],
    [{ text: "⚙️ Настройки", data: "set" }],
  ],
});

const recordsScreen = screen({
  text: "🏆 Рекорды",
  rows: [[{ text: "🏠 Меню", data: "menu" }]],
});

function makeApp(tg: TelegramWebApp | undefined = fakeTelegram().tg) {
  const makeConnection = (callbacks: ConnectionCallbacks) =>
    new Connection({
      url: "ws://test/ws",
      source: { initData: "", startParam: null, devUser: { id: 1, name: "Тестер" } },
      callbacks,
      socketFactory: () => new FakeSocket(),
    });
  const rendered = render(<App webApp={tg} makeConnection={makeConnection} />);
  return rendered;
}

/** События сокета — под act, чтобы сигналы успели отрисовать DOM. */
const open = (sock: FakeSocket) => act(() => sock.open());
const message = (sock: FakeSocket, obj: unknown) => act(() => sock.message(obj));
const drop = (sock: FakeSocket) => act(() => sock.drop());
const tick = (ms: number) => act(async () => { await vi.advanceTimersByTimeAsync(ms); });

beforeEach(() => {
  FakeSocket.created = [];
  vi.useFakeTimers();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
});

describe("App и соединение", () => {
  it("кадр экрана рисуется, кнопка шлёт press с selectionChanged", () => {
    const { tg, calls } = fakeTelegram();
    const { container } = makeApp(tg);
    const sock = FakeSocket.created[0]!;
    void open(sock);
    void message(sock, { type: "screen", seq: null, note: null, screen: recordsScreen });
    const button = container.querySelector<HTMLButtonElement>("button.btn")!;
    expect(button.dataset.payload).toBe("menu");
    fireEvent.click(button);
    expect(calls.selection).toBe(1);
    expect(sock.sent.some((raw) => raw.includes('"type":"press"') && raw.includes('"payload":"menu"'))).toBe(true);
  });

  it("экран с view без компонента — заглушка с плашкой «скоро»", () => {
    const { container } = makeApp();
    const sock = FakeSocket.created[0]!;
    void open(sock);
    // sea рисует M4 — единственный вид без компонента после M3
    const view: View = {
      kind: "sea", title: "⚔️ Морской бой", score: 0, actions: {},
      code: "ABC234", opponent: { name: "🤖", ai: true }, set: "reduced",
      status: "placing", turn: null, thinking: false, timer: null,
      timeouts: { me: 0, them: 0, max: 3 }, last: [],
      own: { rows: 1, cols: 1, cells: [[{ k: "sea" }]] },
      enemy: { rows: 1, cols: 1, cells: [[{ k: "sea" }]] },
      blink: null, result: null, placement: null, invite: null,
    };
    void message(sock, { type: "screen", seq: null, note: null, screen: screen({ view }) });
    expect(container.querySelector(".soon")?.textContent).toContain("скоро");
    expect(container.querySelector(".text")).not.toBeNull();   // универсальный рендер внутри
  });

  it("screen: null не меняет экран, note показывает toast", () => {
    const { container } = makeApp();
    const sock = FakeSocket.created[0]!;
    void open(sock);
    void message(sock, { type: "screen", seq: 1, note: null, screen: recordsScreen });
    void message(sock, { type: "screen", seq: 2, note: "Не ваш ход!", screen: null });
    expect(container.querySelector(".text")?.textContent).toContain("Рекорды");
    expect(container.querySelector(".toast")?.textContent).toBe("Не ваш ход!");
    expect(container.querySelector(".toast")?.classList).not.toContain("toast-top");
  });

  it("на экране игры (есть view) toast сверху — не закрывает подсказку и «Закончить»", () => {
    const { container } = makeApp();
    const sock = FakeSocket.created[0]!;
    void open(sock);
    const view: View = {
      kind: "memo", title: "🃏 Мемо", level: 1, score: 0, combo: "×1", actions: { tap: "t:x:{r}:{c}", skip: "t:x:0:0", quit: "q:x" },
      done: false, pairs: { found: 0, total: 1 }, moves: { made: 0, limit: 2 },
      grid: { rows: 1, cols: 2, cells: [[{ k: "back" }, { k: "back" }]] },
    };
    void message(sock, { type: "screen", seq: 1, note: "✅ Пара!", screen: screen({ view }) });
    expect(container.querySelector(".toast")?.classList).toContain("toast-top");
  });
});

describe("toast и вибрация", () => {
  it("toast живёт 1,5 с, новый заменяет старый", async () => {
    const { tg } = fakeTelegram();
    const { container } = makeApp(tg);
    const sock = FakeSocket.created[0]!;
    void open(sock);
    void message(sock, { type: "screen", seq: 1, note: "✅ Готово", screen: null });
    void message(sock, { type: "screen", seq: 2, note: "Ещё", screen: null });
    expect(container.querySelector(".toast")?.textContent).toBe("Ещё");
    await tick(1400);
    expect(container.querySelector(".toast")).not.toBeNull();
    await tick(200);
    expect(container.querySelector(".toast")).toBeNull();
  });

  it("«Не ваш ход» и «❌» — ошибка, остальное — лёгкий отклик", () => {
    const { tg, haptics } = fakeTelegram();
    makeApp(tg);
    const sock = FakeSocket.created[0]!;
    void open(sock);
    void message(sock, { type: "screen", seq: 1, note: "Не ваш ход!", screen: null });
    void message(sock, { type: "screen", seq: 2, note: "❌ Ошибка", screen: null });
    void message(sock, { type: "screen", seq: 3, note: "✅ Раунд пройден", screen: null });
    expect(haptics).toEqual(["notify:error", "notify:error", "impact:light"]);
  });
});

describe("индикатор связи", () => {
  it("полоса появляется через 1 с после разрыва и исчезает при восстановлении", async () => {
    const { container } = makeApp();
    const sock = FakeSocket.created[0]!;
    void open(sock);
    expect(container.querySelector(".offline-bar")).toBeNull();
    void drop(sock);
    await tick(999);
    expect(container.querySelector(".offline-bar")).toBeNull();
    await tick(1);
    expect(container.querySelector(".offline-bar")?.textContent).toBe("Нет связи…");
    await tick(1000);                                  // пауза переподключения 1 с
    void open(FakeSocket.created[1]!);
    expect(container.querySelector(".offline-bar")).toBeNull();
  });

  it("полоса не остаётся после восстановления на первой паузе", async () => {
    const { container } = makeApp();
    const sock = FakeSocket.created[0]!;
    void open(sock);
    void drop(sock);
    await tick(999);
    expect(container.querySelector(".offline-bar")).toBeNull();   // сразу после разрыва полосы нет
    await tick(1000);                                              // пауза переподключения истекла
    void open(FakeSocket.created[1]!);
    expect(container.querySelector(".offline-bar")).toBeNull();   // восстановились — полосы нет
  });

  it("auth показывает экран «Откройте игры из Telegram» и не переподключается", async () => {
    const { container } = makeApp();
    const sock = FakeSocket.created[0]!;
    void open(sock);
    void message(sock, { type: "error", code: "auth", message: "" });
    expect(container.querySelector(".auth-error")?.textContent).toBe("Откройте игры из Telegram");
    await tick(30_000);
    expect(FakeSocket.created).toHaveLength(1);
  });
});

describe("кнопка «Назад» Telegram", () => {
  it("показывается на экране с кнопкой «Меню», прячется на меню, нажатие шлёт menu", () => {
    const { tg, calls, backHandlers } = fakeTelegram();
    const { container } = makeApp(tg);
    expect(container).not.toBeNull();
    const sock = FakeSocket.created[0]!;
    void open(sock);

    void message(sock, { type: "screen", seq: 1, note: null, screen: recordsScreen });
    expect(calls.backShow).toBe(1);
    expect(calls.backHide).toBe(0);

    void message(sock, { type: "screen", seq: 2, note: null, screen: menuScreen });
    expect(calls.backHide).toBe(1);

    void message(sock, { type: "screen", seq: 3, note: null, screen: recordsScreen });
    expect(calls.backShow).toBe(2);

    expect(backHandlers).toHaveLength(1);
    act(() => backHandlers[0]!());
    expect(sock.sent.some((raw) => raw.includes('"payload":"menu"'))).toBe(true);
  });
});

describe("карточки notice", () => {
  it("идут очередью: кнопка карточки шлёт press и закрывает, крестик закрывает", () => {
    const { container } = makeApp();
    const sock = FakeSocket.created[0]!;
    void open(sock);
    void message(sock, { type: "screen", seq: 1, note: null, screen: menuScreen });

    void message(sock, { type: "notice", screen: screen({ text: "Первая", rows: [[{ text: "👥 Друзья", data: "fr" }]] }) });
    void message(sock, { type: "notice", screen: screen({ text: "Вторая", rows: [] }) });

    const sheet = () => container.querySelector(".notice-sheet")!;
    expect(sheet().textContent).toContain("Первая");

    fireEvent.click(sheet().querySelector<HTMLButtonElement>('button[data-payload="fr"]')!);
    expect(sock.sent.some((raw) => raw.includes('"payload":"fr"'))).toBe(true);
    expect(sheet().textContent).toContain("Вторая");      // следующая из очереди

    fireEvent.click(sheet().querySelector<HTMLButtonElement>(".notice-close")!);
    expect(container.querySelector(".notice-sheet")).toBeNull();
  });
});

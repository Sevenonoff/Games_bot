// Connection: hello (initData / dev_user / start), seq, порядок применения ответов,
// переподключение с паузами 1-2-5-5 и hello без start после разрыва, auth без повторов.
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { Connection, helloSource, wsUrl } from "../../src/connection";
import type { ScreenFrame } from "../../src/protocol";

/** Подделка сокета: тест управляет open()/drop()/message() и смотрит sent. */
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
    if (!this.closed) {
      this.closed = true;
      this.readyState = 3;
      this.onclose?.();
    }
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

const screen = (text: string) => ({ text, rows: [], image: null, view: null });

interface TestSource {
  initData?: string;
  startParam?: string | null;
  devUser?: { id: number; name: string } | null;
}

function makeConnection(source: TestSource, delays: number[]) {
  const frames: ScreenFrame[] = [];
  const notices: unknown[] = [];
  const states: string[] = [];
  const conn = new Connection({
    url: "ws://test/ws",
    source: {
      initData: source.initData ?? "",
      startParam: source.startParam ?? null,
      devUser: source.devUser ?? null,
    },
    callbacks: {
      onFrame: (frame) => frames.push(frame),
      onNotice: (scr) => notices.push(scr),
      onState: (state) => states.push(state),
    },
    socketFactory: () => new FakeSocket(),
    delays,
  });
  return { conn, frames, notices, states };
}

beforeEach(() => {
  FakeSocket.created = [];
  vi.useFakeTimers();
});

afterEach(() => {
  vi.useRealTimers();
});

describe("hello", () => {
  it("несёт initData и start из Telegram", () => {
    const { conn } = makeConnection({ initData: "подпись", startParam: "mp_ABC234" }, [1000]);
    conn.start();
    const sock = FakeSocket.created[0]!;
    sock.open();
    const hello = JSON.parse(sock.sent[0]!);
    expect(hello).toEqual({ type: "hello", client: "1.0.0", initData: "подпись", start: "mp_ABC234" });
  });

  it("без Telegram несёт dev_user вместо initData", () => {
    const { conn } = makeConnection({ devUser: { id: 1, name: "Тестер" } }, [1000]);
    conn.start();
    const sock = FakeSocket.created[0]!;
    sock.open();
    const hello = JSON.parse(sock.sent[0]!);
    expect(hello).toEqual({ type: "hello", client: "1.0.0", dev_user: { id: 1, name: "Тестер" } });
  });

  it("helloSource берёт dev_user и start из адреса страницы", () => {
    const params = new URLSearchParams("?dev_user=7&dev_name=Имя&start=fr_QQ12");
    expect(helloSource(params, null)).toEqual({
      initData: "",
      startParam: "fr_QQ12",
      devUser: { id: 7, name: "Имя" },
    });
    const tg = { initData: "sig", initDataUnsafe: { start_param: "mp_X" } };
    expect(helloSource(new URLSearchParams(""), tg)).toEqual({
      initData: "sig",
      startParam: "mp_X",
      devUser: null,
    });
  });

  it("wsUrl заменяет http→ws и https→wss с путём /ws", () => {
    expect(wsUrl({ protocol: "http:", host: "127.0.0.1:8448" })).toBe("ws://127.0.0.1:8448/ws");
    expect(wsUrl({ protocol: "https:", host: "x.ru" })).toBe("wss://x.ru/ws");
  });
});

describe("press и ответы", () => {
  it("seq растёт с каждым нажатием", () => {
    const { conn } = makeConnection({}, [1000]);
    conn.start();
    const sock = FakeSocket.created[0]!;
    sock.open();
    conn.press("menu");
    conn.press("rec");
    conn.press("new:memo");
    const presses = sock.sent.slice(1).map((raw) => JSON.parse(raw));
    expect(presses.map((p) => p.seq)).toEqual([1, 2, 3]);
    expect(presses.every((p) => p.type === "press")).toBe(true);
    expect(presses.map((p) => p.payload)).toEqual(["menu", "rec", "new:memo"]);
  });

  it("нажатия не блокируются: шлются без ожидания ответа", () => {
    const { conn } = makeConnection({}, [1000]);
    conn.start();
    const sock = FakeSocket.created[0]!;
    sock.open();
    conn.press("a");
    conn.press("b");   // ответа на «a» ещё не было
    expect(sock.sent.filter((raw) => raw.includes("press")).length).toBe(2);
  });

  it("нажатие без открытого сокета теряется, а не копится", () => {
    const { conn } = makeConnection({}, [1000]);
    conn.start();                       // сокет ещё не открыт
    conn.press("menu");
    const sock = FakeSocket.created[0]!;
    sock.open();
    expect(sock.sent.filter((raw) => raw.includes("press")).length).toBe(0);
  });

  it("ответы применяются в порядке прихода", () => {
    const { conn, frames } = makeConnection({}, [1000]);
    conn.start();
    const sock = FakeSocket.created[0]!;
    sock.open();
    conn.press("a");
    conn.press("b");
    sock.message({ type: "screen", seq: 2, note: null, screen: screen("второй") });
    sock.message({ type: "screen", seq: 1, note: null, screen: screen("первый") });
    expect(frames.map((f) => (f.screen as { text: string }).text)).toEqual(["второй", "первый"]);
    expect(frames.map((f) => f.seq)).toEqual([2, 1]);
  });

  it("notice приходит отдельным колбэком", () => {
    const { conn, notices } = makeConnection({}, [1000]);
    conn.start();
    const sock = FakeSocket.created[0]!;
    sock.open();
    sock.message({ type: "notice", screen: screen("друг сыграл") });
    expect(notices).toHaveLength(1);
  });

  it("мусорный кадр не роняет соединение", () => {
    const { conn, frames } = makeConnection({}, [1000]);
    conn.start();
    const sock = FakeSocket.created[0]!;
    sock.open();
    sock.onmessage?.({ data: "{не json" });
    sock.message({ type: "screen", seq: null, note: null, screen: screen("кадр") });
    expect(frames).toHaveLength(1);
  });
});

describe("переподключение", () => {
  it("паузы 1, 2, 5, 5… и hello без start после разрыва", () => {
    const { conn } = makeConnection({ startParam: "mp_AB" }, [1000, 2000, 5000]);
    conn.start();
    const first = FakeSocket.created[0]!;
    first.open();
    expect(JSON.parse(first.sent[0]!).start).toBe("mp_AB");

    // первое соединение оборвалось — пауза 1 с
    first.drop();
    vi.advanceTimersByTime(999);
    expect(FakeSocket.created).toHaveLength(1);
    vi.advanceTimersByTime(1);
    expect(FakeSocket.created).toHaveLength(2);

    // попытки без успеха: пауза растёт 2 с → 5 с → 5 с
    FakeSocket.created[1]!.drop();       // сервер не ответил, соединение не открылось
    vi.advanceTimersByTime(1999);
    expect(FakeSocket.created).toHaveLength(2);
    vi.advanceTimersByTime(1);
    expect(FakeSocket.created).toHaveLength(3);

    FakeSocket.created[2]!.drop();
    vi.advanceTimersByTime(4999);
    expect(FakeSocket.created).toHaveLength(3);
    vi.advanceTimersByTime(1);
    expect(FakeSocket.created).toHaveLength(4);

    FakeSocket.created[3]!.drop();
    vi.advanceTimersByTime(4999);
    expect(FakeSocket.created).toHaveLength(4);
    vi.advanceTimersByTime(1);
    expect(FakeSocket.created).toHaveLength(5);

    // восстановились: hello без start
    const restored = FakeSocket.created[4]!;
    restored.open();
    expect(JSON.parse(restored.sent[0]!)).not.toHaveProperty("start");
  });

  it("после успешного соединения паузы начинаются заново с 1 с", () => {
    const { conn } = makeConnection({}, [1000, 2000, 5000]);
    conn.start();
    const first = FakeSocket.created[0]!;
    first.open();
    first.drop();
    vi.advanceTimersByTime(1000);
    FakeSocket.created[1]!.open();      // восстановились
    FakeSocket.created[1]!.drop();
    vi.advanceTimersByTime(1000);       // снова первая пауза, а не вторая
    expect(FakeSocket.created).toHaveLength(3);
  });

  it("auth останавливает переподключение", () => {
    const { conn, states } = makeConnection({}, [1000]);
    conn.start();
    const sock = FakeSocket.created[0]!;
    sock.open();
    sock.message({ type: "error", code: "auth", message: "" });
    expect(states).toContain("auth_error");
    sock.drop();
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.created).toHaveLength(1);
  });

  it("bad_request и server не рвут соединение", () => {
    const { conn, frames } = makeConnection({}, [1000]);
    conn.start();
    const sock = FakeSocket.created[0]!;
    sock.open();
    sock.message({ type: "error", code: "server", seq: 1 });
    sock.message({ type: "screen", seq: null, note: null, screen: screen("жив") });
    expect(frames).toHaveLength(1);
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.created).toHaveLength(1);
  });

  it("stop прекращает попытки", () => {
    const { conn } = makeConnection({}, [1000]);
    conn.start();
    FakeSocket.created[0]!.drop();
    conn.stop();
    vi.advanceTimersByTime(60_000);
    expect(FakeSocket.created).toHaveLength(1);
  });
});

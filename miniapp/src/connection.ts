// WebSocket-клиент: hello, press с seq, переподключение с паузами 1, 2, 5, 5… с.
// Ответы сервера применяются в порядке прихода; нажатия не блокируют друг друга —
// сервер сам сериализует их под замком игрока.
import type { HelloMessage, Screen, ScreenFrame, ServerMessage } from "./protocol";
import { CLIENT_VERSION } from "./protocol";
import type { TelegramWebApp } from "./telegram";

export type ConnState =
  | "connecting"    // соединение открывается
  | "online"        // соединение установлено, hello отправлен
  | "waiting"       // пауза перед следующим подключением
  | "auth_error";   // сервер отверг вход — переподключаться нельзя

/** Минимальный сокет: настоящий WebSocket или подделка в тестах. */
export interface WebSocketLike {
  send(data: string): void;
  close(): void;
  readonly readyState: number;   // 1 — OPEN, как у WebSocket
  onopen: (() => void) | null;
  onclose: (() => void) | null;
  onerror: (() => void) | null;
  onmessage: ((event: { data: string }) => void) | null;
}

export type SocketFactory = (url: string) => WebSocketLike;

export interface HelloSource {
  initData: string;                                  // Telegram.WebApp.initData, "" если нет
  startParam: string | null;                         // параметр ссылки
  devUser: { id: number; name: string } | null;      // вход без Telegram: ?dev_user=&dev_name=
}

export interface ConnectionCallbacks {
  onFrame(frame: ScreenFrame): void;   // кадр-экран (ответ или правка по таймеру)
  onNotice(screen: Screen): void;      // карточка-уведомление
  onState(state: ConnState): void;
}

export interface ConnectionOptions {
  url: string;
  source: HelloSource;
  callbacks: ConnectionCallbacks;
  socketFactory?: SocketFactory;
  delays?: number[];                   // паузы переподключения, по умолчанию 1, 2, 5, 5…
}

const OPEN = 1;
const DEFAULT_DELAYS = [1000, 2000, 5000];

/** location.origin с заменой http→ws и путём /ws. */
export function wsUrl(loc: { protocol: string; host: string }): string {
  const proto = loc.protocol === "https:" ? "wss" : "ws";
  return `${proto}://${loc.host}/ws`;
}

/** Поля hello: initData из Telegram; без Telegram — dev_user из адреса, start — из ?start=. */
export function helloSource(params: URLSearchParams, tg: Pick<TelegramWebApp, "initData" | "initDataUnsafe"> | null): HelloSource {
  const initData = tg?.initData ?? "";
  const urlStart = params.get("start");
  const startParam = initData ? (tg?.initDataUnsafe.start_param ?? null) : urlStart;
  let devUser: HelloSource["devUser"] = null;
  if (!initData) {
    const id = Number(params.get("dev_user"));
    const name = params.get("dev_name");
    if (Number.isInteger(id) && id > 0 && name) devUser = { id, name };
  }
  return { initData, startParam, devUser };
}

/** Настоящий WebSocket, приведённый к WebSocketLike без приведения типов. */
const browserSocket: SocketFactory = (url) => {
  const ws = new WebSocket(url);
  return {
    send: (data) => ws.send(data),
    close: () => ws.close(),
    get readyState() { return ws.readyState; },
    set onopen(cb: (() => void) | null) { ws.onopen = cb === null ? null : () => cb(); },
    set onclose(cb: (() => void) | null) { ws.onclose = cb === null ? null : () => cb(); },
    set onerror(cb: (() => void) | null) { ws.onerror = cb === null ? null : () => cb(); },
    set onmessage(cb: ((event: { data: string }) => void) | null) {
      ws.onmessage = cb === null ? null : (ev) => cb({ data: String(ev.data) });
    },
  };
};

export class Connection {
  private socket: WebSocketLike | null = null;
  private seq = 0;
  private attempts = 0;      // после первого hello start больше не шлём (tz-m2 §3.2)
  private retryIndex = 0;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private stopped = false;
  private authFailed = false;
  private readonly opts: ConnectionOptions;

  constructor(opts: ConnectionOptions) {
    this.opts = opts;
  }

  start(): void {
    this.openSocket();
  }

  /** Нажатие: seq присваивается здесь. Без открытого сокета нажатие теряется —
   *  не блокируется и не копится, повторное нажатие пошлёт его заново. */
  press(payload: string): void {
    if (this.socket?.readyState !== OPEN) return;
    this.seq += 1;
    this.socket.send(JSON.stringify({ type: "press", payload, seq: this.seq }));
  }

  stop(): void {
    this.stopped = true;
    this.clearTimer();
    this.socket?.close();   // onclose молчит: stopped
    this.socket = null;
  }

  // --- внутреннее ---

  private openSocket(): void {
    if (this.stopped || this.authFailed) return;
    this.opts.callbacks.onState("connecting");
    const factory = this.opts.socketFactory ?? browserSocket;
    const socket = factory(this.opts.url);
    this.socket = socket;
    socket.onopen = () => {
      this.attempts += 1;
      this.retryIndex = 0;
      this.opts.callbacks.onState("online");
      socket.send(JSON.stringify(this.hello()));
    };
    socket.onmessage = (ev) => this.onMessage(ev.data);
    socket.onclose = () => {
      this.socket = null;
      if (!this.stopped && !this.authFailed) this.scheduleReconnect();
    };
    socket.onerror = () => { /* за onerror всегда следует onclose */ };
  }

  private hello(): HelloMessage {
    const hello: HelloMessage = { type: "hello", client: CLIENT_VERSION };
    const { source } = this.opts;
    if (source.initData) hello.initData = source.initData;
    else if (source.devUser) hello.dev_user = source.devUser;
    if (this.attempts === 1 && source.startParam) hello.start = source.startParam;
    return hello;
  }

  private onMessage(data: string): void {
    let msg: ServerMessage;
    try {
      msg = JSON.parse(data) as ServerMessage;
    } catch {
      return;                        // мусорный кадр — игнорируем, соединение живо
    }
    switch (msg.type) {
      case "screen":
        this.opts.callbacks.onFrame(msg);
        break;
      case "notice":
        this.opts.callbacks.onNotice(msg.screen);
        break;
      case "error":
        if (msg.code === "auth") {
          this.authFailed = true;    // вход отвергнут: без переподключения
          this.opts.callbacks.onState("auth_error");
          this.socket?.close();
        }
        break;                       // bad_request/server — соединение остаётся
    }
  }

  private scheduleReconnect(): void {
    const delays = this.opts.delays ?? DEFAULT_DELAYS;
    const delay = delays[Math.min(this.retryIndex, delays.length - 1)];
    this.retryIndex += 1;
    this.opts.callbacks.onState("waiting");
    this.timer = setTimeout(() => this.openSocket(), delay);
  }

  private clearTimer(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
  }
}

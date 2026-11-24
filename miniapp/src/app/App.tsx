// Корневой компонент: владеет соединением и всем состоянием приложения (экран, toast,
// очередь карточек-уведомлений, индикатор связи). Состояние — сигналы, созданные внутри
// App: глобального состояния вне App нет.
import { useEffect, useMemo, useRef } from "preact/hooks";
import type { VNode } from "preact";
import { signal } from "@preact/signals";
import type { Signal } from "@preact/signals";
import type { ConnState, ConnectionCallbacks } from "../connection";
import { Connection, helloSource, wsUrl } from "../connection";
import type { Screen, ScreenFrame } from "../protocol";
import type { TelegramWebApp } from "../telegram";
import { isMenuScreen } from "./GenericScreen";
import { GenericScreen } from "./GenericScreen";
import { Placeholder } from "../games/Placeholder";
import { games } from "../games/registry";

const NOTE_MS = 1500;        // toast живёт 1,5 с, новый заменяет старый
const OFFLINE_BAR_MS = 1000; // полоса «Нет связи…» появляется через 1 с без соединения

interface AppUi {
  screen: Signal<Screen | null>;
  notices: Signal<Screen[]>;
  note: Signal<string | null>;
  offlineBar: Signal<boolean>;
  authError: Signal<boolean>;
}

export interface AppProps {
  /** Тесты подменяют Telegram; прод берёт window.Telegram сам. */
  webApp?: TelegramWebApp;
  /** Тесты создают соединение с фальшивым сокетом; прод — настоящий WebSocket. */
  makeConnection?: (callbacks: ConnectionCallbacks) => Connection;
}

export function App(props: AppProps): VNode {
  const tg = props.webApp ?? window.Telegram?.WebApp ?? null;

  const ui = useMemo<AppUi>(() => ({
    screen: signal<Screen | null>(null),
    notices: signal<Screen[]>([]),
    note: signal<string | null>(null),
    offlineBar: signal(false),
    authError: signal(false),
  }), []);

  const noteTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const offlineTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  function showNote(text: string): void {
    ui.note.value = text;
    if (noteTimer.current !== null) clearTimeout(noteTimer.current);
    noteTimer.current = setTimeout(() => { ui.note.value = null; }, NOTE_MS);
    // ошибка — резкая вибрация, обычное уведомление — лёгкий отклик
    const isError = text.includes("❌") || text.includes("Не ваш ход");
    if (isError) tg?.HapticFeedback.notificationOccurred("error");
    else tg?.HapticFeedback.impactOccurred("light");
  }

  function setState(state: ConnState): void {
    if (state === "auth_error") {
      ui.authError.value = true;
      ui.offlineBar.value = false;
      if (offlineTimer.current !== null) {
        clearTimeout(offlineTimer.current);
        offlineTimer.current = null;
      }
      return;
    }
    if (state === "online") {
      ui.offlineBar.value = false;
      if (offlineTimer.current !== null) {
        clearTimeout(offlineTimer.current);
        offlineTimer.current = null;
      }
    } else if (offlineTimer.current === null) {
      offlineTimer.current = setTimeout(() => {
        offlineTimer.current = null;
        ui.offlineBar.value = true;
      }, OFFLINE_BAR_MS);
    }
  }

  const connRef = useRef<Connection | null>(null);
  if (connRef.current === null) {
    const callbacks: ConnectionCallbacks = {
      onFrame: (frame: ScreenFrame) => {
        if (frame.screen !== null) ui.screen.value = frame.screen;
        if (frame.note !== null) showNote(frame.note);
      },
      onNotice: (screen: Screen) => { ui.notices.value = [...ui.notices.value, screen]; },
      onState: setState,
    };
    connRef.current = props.makeConnection !== undefined
      ? props.makeConnection(callbacks)
      : new Connection({
          url: wsUrl(window.location),
          source: helloSource(new URLSearchParams(window.location.search), tg),
          callbacks,
        });
  }

  useEffect(() => {
    connRef.current!.start();
    return () => {
      connRef.current!.stop();
      if (noteTimer.current !== null) clearTimeout(noteTimer.current);
      if (offlineTimer.current !== null) clearTimeout(offlineTimer.current);
    };
  }, []);

  function press(payload: string): void {
    tg?.HapticFeedback.selectionChanged();
    connRef.current!.press(payload);
  }

  const pressRef = useRef(press);
  pressRef.current = press;

  // Системная кнопка «Назад» дублирует кнопку «Меню», когда она есть и экран не меню.
  const backShown = useRef(false);
  const screen = ui.screen.value;
  useEffect(() => {
    if (tg === null || screen === null) return;
    const want = !isMenuScreen(screen) && screen.rows.some((r) => r.some((b) => b.data === "menu"));
    if (want && !backShown.current) {
      tg.BackButton.show();
      backShown.current = true;
    } else if (!want && backShown.current) {
      tg.BackButton.hide();
      backShown.current = false;
    }
  }, [screen]);

  useEffect(() => {
    if (tg === null) return;
    const back = () => pressRef.current("menu");
    tg.BackButton.onClick(back);
    return () => tg.BackButton.offClick(back);
  }, [tg]);

  if (ui.authError.value) {
    return <div class="auth-error">Откройте игры из Telegram</div>;
  }

  const notices = ui.notices.value;
  return (
    <div class="app">
      {ui.offlineBar.value && <div class="offline-bar" role="alert">Нет связи…</div>}
      {screen === null
        ? null
        : screen.view === null
          ? <GenericScreen screen={screen} press={press} />
          : renderGame(screen, press, ui.note.value, tg)}
      {ui.note.value !== null && (
        // на экране игры toast сверху, поверх шапки: внизу у игр подсказка и «Закончить»
        <div class={screen !== null && screen.view !== null ? "toast toast-top" : "toast"} role="status">
          {ui.note.value}
        </div>
      )}
      {notices.length > 0 && (
        <NoticeSheet
          screen={notices[0]}
          press={press}
          onClose={() => { ui.notices.value = notices.slice(1); }}
        />
      )}
    </div>
  );
}

function renderGame(screen: Screen, press: (payload: string) => void, note: string | null,
                    tg: TelegramWebApp | null): VNode {
  const view = screen.view!;
  const Game = games[view.kind] ?? Placeholder;
  return <Game view={view} screen={screen} press={press} note={note} tg={tg} />;
}

/** Карточка-уведомление (bottom sheet): текст, картинка и кнопки — тем же универсальным
 *  рендером. Кнопка шлёт press и закрывает карточку, крестик — просто закрывает. */
function NoticeSheet(props: { screen: Screen; press: (payload: string) => void; onClose: () => void }): VNode {
  return (
    <div class="notice-backdrop">
      <div class="notice-sheet" role="dialog" aria-label="Уведомление">
        <button type="button" class="notice-close" aria-label="Закрыть" onClick={props.onClose}>✕</button>
        <GenericScreen
          screen={props.screen}
          press={(payload) => {
            props.onClose();
            props.press(payload);
          }}
        />
      </div>
    </div>
  );
}

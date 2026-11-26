// Морской бой (tz-m4): приглашение, расстановка перетаскиванием, ожидание, бой с
// миганием потопленного корабля и итог. Правил на клиенте нет: тень при перетаскивании —
// только подсказка вида, окончательно решает сервер; payload'ы — из view.actions.
import type { VNode } from "preact";
import { useCallback, useEffect, useMemo, useRef, useState } from "preact/hooks";
import type { GameProps } from "../registry";
import type { Button, SeaCell, SeaView } from "../../protocol";
import { renderTelegramHtml } from "../../app/html";
import {
  canPlace, cellFromPoint, cellKey, placePayload, shipCells, shipCellsFromStart,
} from "./geometry";
import "./Sea.css";

const GAP = 3;             // зазор клеток сетки (Sea.css .scell gap)
const CELL_MIN = 30;
const OWN_SHARE = 0.6;     // своё поле — ≈60% ширины (tz-m4 §3)

type Board = SeaView["own"];

/** Подписи строки состояния — служебные подписи клиента (tz-m4 §2). */
const RESULT_MARK: Record<SeaView["last"][number]["result"], string> = { miss: "💠", hit: "💥", sunk: "💢" };
const BY_LABEL = { me: "Вы", them: "Соперник" } as const;

/** Кнопка экрана с data == payload, если она сейчас на экране (наличие и подпись — с сервера). */
function actionButton(rows: Button[][], payload: string): Button | undefined {
  return rows.flat().find((b) => b.data === payload);
}

/** Кнопки итога и прочие экранные (не из actions), в порядке экрана. */
function rowButtons(rows: Button[][], skip: Set<string>): Button[] {
  return rows.flat().filter((b) => !skip.has(b.data));
}

/** Клетки поля боя. */
function BoardView(props: {
  board: Board;
  cell: number;
  fire?: string;             // шаблон actions.fire — только у поля соперника в свой ход
  blinkCells?: [number, number][];
  blinkFrame?: "hit" | "sunk";
  label: string;
  onFire?: (payload: string) => void;
}): VNode {
  const { board, cell, fire, blinkCells, blinkFrame, label, onFire } = props;
  const blink = useMemo(() => new Set((blinkCells ?? []).map(([r, c]) => `${r}:${c}`)), [blinkCells]);
  const canFire = fire !== undefined && onFire !== undefined;
  return (
    <div class="sboard-wrap">
      <div class="sboard-label">{label}</div>
      <div class="sboard" style={{ gridTemplateColumns: `repeat(${board.cols}, ${cell}px)` }}>
        {board.cells.map((row, r) => row.map((c: SeaCell, col) => {
          const payload = fire?.replace("{r}", String(r)).replace("{c}", String(col));
          const key = `${r}:${col}`;
          const shooting = canFire && c.k === "sea" && payload !== undefined;
          const blinkOn = blink.has(key);
          const shown = blinkOn ? blinkFrame : c.k;
          return (
            <button
              key={key}
              type="button"
              class={`scell k-${c.k}${blinkOn ? ` blink-${shown}` : ""}`}
              data-payload={shooting ? payload : undefined}
              disabled={!shooting}
              onClick={() => shooting && onFire!(payload!)}
            >
              {shown === "miss" ? <span class="mark-miss" /> : null}
              {shown === "hit" ? "💥" : null}
              {shown === "sunk" ? "💢" : null}
              {shown === "ship" ? <span class="mark-ship" /> : null}
            </button>
          );
        }))}
      </div>
    </div>
  );
}

/** Кольцо таймера хода вокруг индикатора: убывает между кадрами (CSS transition). */
function TurnRing(props: { left: number; total: number; overtime?: boolean }): VNode {
  const ring = useRef<SVGCircleElement | null>(null);
  const from = Math.max(0, props.left);
  useEffect(() => {
    const el = ring.current;
    if (el === null) return;
    const full = 2 * Math.PI * 15;
    el.style.transition = "none";
    el.style.strokeDashoffset = props.overtime || from === 0 ? String(full) : "0";
    void el.getBoundingClientRect();
    if (!props.overtime && from > 0) {
      el.style.transition = `stroke-dashoffset ${from}s linear`;
      el.style.strokeDashoffset = String(full);
    }
  }, [from, props.overtime]);
  const low = from <= 5 || props.overtime === true;
  return (
    <span class={"ring" + (low ? " ring-low" : "")} aria-hidden="true">
      <svg viewBox="0 0 36 36" width="36" height="36">
        <circle class="ring-bg" cx="18" cy="18" r="15" />
        <circle class="ring-fg" cx="18" cy="18" r="15" ref={ring}
                stroke-dasharray={2 * Math.PI * 15} />
      </svg>
      <span class="ring-mark">⏱</span>
    </span>
  );
}

export function Sea(props: GameProps<SeaView>): VNode {
  const { view } = props;
  const quit = view.actions.surrender;

  // --- вибрация сверх каркаса (tz-m4 §6): по разнице кадров, один раз на событие ---
  const prev = useRef<{ last: string | null; result: string | null } | null>(null);
  useEffect(() => {
    const key = view.last[0] ? `${view.last[0].by}:${view.last[0].result}` : null;
    const before = prev.current;
    prev.current = { last: key, result: view.result === null ? null : String(view.result.won) };
    if (before === null) return;
    if (view.last[0] && key !== before.last) {
      if (view.last[0].by === "me" && view.last[0].result !== "miss") props.tg?.HapticFeedback.impactOccurred("medium");
      if (view.last[0].by === "them" && view.last[0].result !== "miss") props.tg?.HapticFeedback.impactOccurred("heavy");
    }
    if (view.result !== null && (before.result === null || before.result !== String(view.result.won))) {
      props.tg?.HapticFeedback.notificationOccurred(view.result.won ? "success" : "error");
    }
  }, [props.tg, view.last, view.result]);

  // --- сдача/отмена: подтверждение (tz-m4 §3) ---
  const confirmSurrender = useCallback(() => {
    const inBattle = view.status === "active";
    const text = inBattle ? "Сдаться? Это поражение." : "Отменить партию?";
    const ask = (ok: boolean) => { if (ok) props.press(quit); };
    if (props.tg !== null) props.tg.showConfirm(text, ask);
    else ask(window.confirm(text));
  }, [props, view.status, quit]);

  const rows = props.screen.rows;
  const surrenderButton = actionButton(rows, quit);
  const menuButton = actionButton(rows, "menu");
  const resetButton = actionButton(rows, view.actions.reset);
  const readyButton = actionButton(rows, view.actions.ready);
  const cancelButton = actionButton(rows, view.actions.cancel_invite);

  // --- приглашение: копирование кода (tz-m4 §5) ---
  const [copied, setCopied] = useState(false);
  const copyCode = useCallback(() => {
    if (view.invite === null) return;
    void navigator.clipboard?.writeText(view.invite.code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    }).catch(() => {});
  }, [view.invite]);

  // --- расстановка: док, ориентация, перетаскивание (tz-m4 §4) ---
  const [dragVertical, setDragVertical] = useState(false);
  const [drag, setDrag] = useState<{ size: number } | null>(null);
  const [pointerCell, setPointerCell] = useState<{ r: number; c: number } | null>(null);
  const gridRef = useRef<HTMLDivElement | null>(null);
  const [gridCell, setGridCell] = useState(CELL_MIN);

  // док: sizes минус длины уже зафиксированных кораблей, от большого к маленькому
  const dock = useMemo(() => {
    if (view.placement === null) return [];
    const left = [...view.placement.sizes].sort((a, b) => b - a);
    for (const ship of view.placement.fixed) {
      const i = left.indexOf(ship.length);
      if (i >= 0) left.splice(i, 1);
    }
    return left;
  }, [view.placement]);

  // sent ожидаемого place: после кадра, где current — наш корабль и note без ошибки, шлём fix
  const pendingPlace = useRef<{ cells: string } | null>(null);
  const currentKey = (view.placement?.current ?? []).map(([r, c]) => `${r}:${c}`).join(";") ?? "";
  useEffect(() => {
    if (pendingPlace.current === null) return;
    const expected = pendingPlace.current;
    if (currentKey === expected.cells) {
      pendingPlace.current = null;
      props.press(view.actions.fix);                 // поставлен — зафиксировать
    } else if (props.note !== null) {
      pendingPlace.current = null;                   // ошибка: сервер отклонил, корабль в доке
    }
  }, [currentKey, props.note]);                      // eslint-disable-line react-hooks/exhaustive-deps

  const startDrag = (size: number) => setDrag({ size });

  const onGridMove = (e: PointerEvent) => {
    if (drag === null || gridRef.current === null) return;
    const rect = gridRef.current.getBoundingClientRect();
    setPointerCell(cellFromPoint(e.clientX - rect.left, e.clientY - rect.top, gridCell, GAP, view.own.rows, view.own.cols));
  };

  const onGridUp = (e: PointerEvent) => {
    if (drag === null || view.placement === null) return;
    const rect = gridRef.current?.getBoundingClientRect();
    const drop = rect === undefined ? null
      : cellFromPoint(e.clientX - rect.left, e.clientY - rect.top, gridCell, GAP, view.own.rows, view.own.cols);
    setDrag(null);
    setPointerCell(null);
    if (drop === null) return;                       // унесли обратно в док
    const cells = shipCells(drop, drag.size, dragVertical);
    pendingPlace.current = { cells: cells.map(cellKey).join(";") };
    props.press(placePayload(view.actions.place, drop, dragVertical));
  };

  useEffect(() => {
    if (drag === null) return;
    window.addEventListener("pointermove", onGridMove);
    window.addEventListener("pointerup", onGridUp);
    return () => {
      window.removeEventListener("pointermove", onGridMove);
      window.removeEventListener("pointerup", onGridUp);
    };
  }, [drag, dragVertical, gridCell, view.placement]);

  // --- размер клетки боя: из размеров зоны (ResizeObserver), поле соперника во всю ширину ---
  const battleRef = useRef<HTMLDivElement | null>(null);
  const [battleSize, setBattleSize] = useState({ w: 360, h: 420 });
  const sideBySide = battleSize.w > 700;
  useEffect(() => {
    const zone = battleRef.current;
    if (zone === null) return;
    const measure = () => setBattleSize({ w: zone.clientWidth, h: zone.clientHeight });
    measure();
    if (typeof ResizeObserver === "undefined") return;   // jsdom
    const observer = new ResizeObserver(measure);
    observer.observe(zone);
    return () => observer.disconnect();
  }, []);
  const enemyCell = Math.max(CELL_MIN, Math.floor(Math.min(
    (battleSize.w - 16 - GAP * 6) / 7,
    ((battleSize.h - 24) / (sideBySide ? 8 : 16)) - GAP,
  )));
  const ownCell = Math.max(24, Math.floor(enemyCell * OWN_SHARE * 0.92));

  // --- расстановка: таймер с убыванием между редкими кадрами ---
  const [left, setLeft] = useState(view.placement?.left ?? 0);
  const leftRef = useRef(view.placement?.left ?? 0);
  useEffect(() => {
    if (view.placement === null) return;
    leftRef.current = view.placement.left;
    setLeft(view.placement.left);
    const timer = setInterval(() => {
      leftRef.current = Math.max(0, leftRef.current - 1);
      setLeft(leftRef.current);
    }, 1000);
    return () => clearInterval(timer);
  }, [view.placement?.left]);                          // eslint-disable-line react-hooks/exhaustive-deps

  // --- вибро-строка состояния боя ---
  const statusLine = view.thinking ? "Компьютер думает…"
    : view.turn === "me" ? "Ваш ход"
      : view.turn === "them" ? "Ход противника"
        : view.status === "waiting_ready" ? "Ждём соперника…"
          : "";

  // тень перетаскиваемого корабля: зелёная/красная — только подсказка вида
  const shadow = useMemo(() => {
    if (drag === null || pointerCell === null) return null;
    const cells = shipCells(pointerCell, drag.size, dragVertical);
    const busy = new Set<string>();
    for (const ship of view.placement?.fixed ?? []) for (const [r, c] of ship) busy.add(cellKey({ r, c }));
    for (const c of view.placement?.forbidden ?? []) busy.add(cellKey({ r: c[0], c: c[1] }));
    return { cells, ok: canPlace(cells, view.own.rows, view.own.cols, busy) };
  }, [drag, pointerCell, dragVertical, view.placement]);
  const shadowSet = useMemo(() => new Set(shadow?.cells.map(cellKey) ?? []), [shadow]);
  const currentSet = useMemo(
    () => new Set((view.placement?.current ?? []).map(([r, c]) => `${r}:${c}`)),
    [view.placement]);

  const blink = view.blink;
  const myFire = view.turn === "me" && view.status === "active" && !view.thinking
    ? view.actions.fire : undefined;
  const inBattle = view.status === "active" || view.status === "finished";
  const reasonText = view.result === null ? "" : view.result.reason === "sunk"
    ? "Все корабли соперника потоплены"
    : view.result.reason === "timeouts" ? "Три пропуска хода — техническое поражение"
      : "Сдача";

  if (view.status === "waiting" && view.invite !== null) {
    return (
      <div class="game game-sea" data-status="waiting" data-turn="">
        <div class="invite">
          <div class="invite-title">Приглашение в бой</div>
          <div class="invite-code">{view.invite.code}</div>
          <button type="button" class="btn" onClick={() =>
            props.tg?.openTelegramLink("https://t.me/share/url?url=" + encodeURIComponent(view.invite!.link))}>
            Отправить другу
          </button>
          <button type="button" class="btn" onClick={copyCode}>Скопировать код</button>
          <div class="invite-copied">{copied ? "Скопировано" : ""}</div>
          {cancelButton !== undefined && (
            <button type="button" class="btn quit" data-payload={cancelButton.data}
                    onClick={() => props.press(cancelButton.data)}>{cancelButton.text}</button>
          )}
          {menuButton !== undefined && (
            <button type="button" class="btn quit" data-payload={menuButton.data}
                    onClick={() => props.press(menuButton.data)}>{menuButton.text}</button>
          )}
        </div>
      </div>
    );
  }

  return (
    <div class="game game-sea" data-status={view.status} data-turn={view.turn ?? ""}>
      {inBattle && (
        <div class="battle-top">
          <span class="status-line">
            {view.status === "active" && (view.timer !== null || view.thinking)
              ? <TurnRing left={view.timer?.left ?? 0} total={view.timer?.total ?? 1} overtime={view.timer === null && view.thinking} />
              : null}
            {statusLine}
          </span>
          {(view.timeouts.me > 0 || view.timeouts.them > 0) && (
            <span class="timeouts">Пропуски: вы {view.timeouts.me}/{view.timeouts.max} · соперник {view.timeouts.them}/{view.timeouts.max}</span>
          )}
          {view.last.slice(0, 2).map((l, i) => (
            <div class="last-line" key={i}>{BY_LABEL[l.by]}: {RESULT_MARK[l.result]}</div>
          ))}
        </div>
      )}

      {view.status === "placing" || view.status === "waiting_ready" ? (
        <>
          {view.status === "placing" && (
            <div class="placing-top">
              <span>Расстановка: {left} с</span>
              <button type="button" class="btn rotate" onClick={() => setDragVertical((v) => !v)}>Повернуть</button>
            </div>
          )}
          {view.status === "waiting_ready" && <div class="placing-top"><span>Ждём соперника…</span></div>}
          <div class="placing-board" style={{ gridTemplateColumns: `repeat(${view.own.cols}, ${gridCell}px)` }}
               ref={gridRef}
               onPointerMove={(e) => onGridMove(e as unknown as PointerEvent)}
               onPointerUp={(e) => onGridUp(e as unknown as PointerEvent)}>
            {view.own.cells.map((row, r) => row.map((c: SeaCell, col) => {
              const key = `${r}:${col}`;
              const isShadow = shadowSet.has(key);
              const isCurrent = currentSet.has(key);
              return (
                <button
                  key={key}
                  type="button"
                  class={`scell k-${c.k}${isShadow ? ` shadow-${shadow!.ok ? "ok" : "bad"}` : ""}${isCurrent ? " current" : ""}`}
                  data-payload={undefined}
                >
                  {isShadow || isCurrent
                    ? ""
                    : c.k === "ship" ? <span class="mark-ship" /> : c.k === "miss" ? <span class="mark-miss" /> : null}
                </button>
              );
            }))}
          </div>
          {view.status === "placing" && (
            <div class="dock">
              {dock.map((size) => (
                <button key={size} type="button" class="dock-ship"
                        onPointerDown={() => startDrag(size)}>
                  <span class="dock-hull">{shipCellsFromStart({ r: 0, c: 0 }, size, false).map((_, i) => <i key={i} />)}</span>
                </button>
              ))}
              {dock.length === 0 && <span class="dock-empty">Все корабли на месте</span>}
            </div>
          )}
        </>
      ) : inBattle ? (
        <div class={"battle" + (sideBySide ? " side-by-side" : "")} ref={battleRef}>
          <BoardView
            board={view.enemy}
            cell={enemyCell}
            label="Поле соперника"
            fire={myFire}
            blinkCells={blink?.board === "enemy" ? blink.cells : undefined}
            blinkFrame={blink?.board === "enemy" ? blink.frame : undefined}
            onFire={props.press}
          />
          <BoardView
            board={view.own}
            cell={ownCell}
            label="Ваши корабли"
            blinkCells={blink?.board === "own" ? blink.cells : undefined}
            blinkFrame={blink?.board === "own" ? blink.frame : undefined}
          />
        </div>
      ) : null}

      {view.result !== null && (
        <div class="result-card">
          <div class={"result-title" + (view.result.won ? " win" : " lose")}>
            {view.result.won ? "🏆 Победа!" : "💀 Поражение"}
          </div>
          <div class="result-reason">{reasonText}</div>
          <div class="result-score">Очки: {view.result.score}</div>
          {view.result.rating !== null && (
            <div class="result-rating">Рейтинг: {view.result.rating} {view.result.delta !== null
              ? `(${view.result.delta > 0 ? "+" : ""}${view.result.delta})` : ""}</div>
          )}
          {view.result.journey.map((line, i) => (
            <div class="result-journey" key={i}>{renderTelegramHtml(line)}</div>
          ))}
        </div>
      )}

      <div class="sea-actions">
        {resetButton !== undefined && (
          <button type="button" class="btn" data-payload={resetButton.data}
                  onClick={() => props.press(resetButton.data)}>{resetButton.text}</button>
        )}
        {readyButton !== undefined && (
          <button type="button" class="btn primary" data-payload={readyButton.data}
                  onClick={() => props.press(readyButton.data)}>{readyButton.text}</button>
        )}
        {surrenderButton !== undefined && (
          <button type="button" class="btn" data-payload={surrenderButton.data}
                  onClick={confirmSurrender}>{surrenderButton.text}</button>
        )}
        {rowButtons(rows, new Set([quit, view.actions.reset, view.actions.ready, view.actions.cancel_invite]))
          .filter((b) => view.status === "finished")
          .map((b, i) => (
            <button key={i} type="button" class={"btn" + (i === 0 ? " primary" : "")} data-payload={b.data}
                    onClick={() => props.press(b.data)}>{b.text}</button>
          ))}
        {menuButton !== undefined && (
          <button type="button" class="btn" data-payload={menuButton.data}
                  onClick={() => props.press(menuButton.data)}>{menuButton.text}</button>
        )}
      </div>
    </div>
  );
}

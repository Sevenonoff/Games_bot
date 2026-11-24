// Общие части экранов игр (tz-m3 §1.1): шапка, поле с подбором размера клетки,
// нажатое состояние клетки, подстановка {r}/{c}, кнопка «Закончить», вибрация кадра.
// Сюда же смотрят CSS-файлы игр: классы game/game-header/field/gcell заданы в common.css.
import type { ComponentChild, VNode } from "preact";
import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "preact/hooks";
import { renderTelegramHtml } from "../../app/html";
import type { Screen } from "../../protocol";
import type { TelegramWebApp } from "../../telegram";
import "./common.css";

/** Payload нажатия клетки: шаблон actions.tap с подставленными координатами. */
export function tapPayload(tap: string, r: number, c: number): string {
  return tap.replace("{r}", String(r)).replace("{c}", String(c));
}

/** Наибольший квадрат, при котором поле влезает в ширину экрана минус 16 px и в высоту
 *  зоны (tz-m3 §1.3). Ниже 30 px клетка не уменьшается — зона получает прокрутку.
 *  В jsdom размеров нет — считаем от типичного телефона 360×560 (для снимков DOM). */
export function useCellSize(zone: HTMLElement | null, rows: number, cols: number): number {
  const [size, setSize] = useState(() => cellFrom(360, 560, rows, cols));
  useLayoutEffect(() => {
    if (zone === null) return;
    const measure = () => setSize(cellFrom(zone.clientWidth, zone.clientHeight, rows, cols));
    measure();
    if (typeof ResizeObserver === "undefined") return;   // jsdom
    const observer = new ResizeObserver(measure);
    observer.observe(zone);
    return () => observer.disconnect();
  }, [zone, rows, cols]);
  return size;
}

function cellFrom(width: number, height: number, rows: number, cols: number): number {
  const gap = 4;
  const cell = Math.floor(Math.min((width - 16 - gap * (cols - 1)) / cols,
    (height - gap * (rows - 1)) / rows));
  return Math.max(30, Math.min(cell, 72));
}

/** Нажатая клетка на 150 мс — единственный отклик до кадра сервера (tz-m3 §1.2). */
export function usePressed(): { pressed: string | null; touch: (key: string) => void } {
  const [pressed, setPressed] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => {
    if (timer.current !== null) clearTimeout(timer.current);
  }, []);
  const touch = useCallback((key: string) => {
    setPressed(key);
    if (timer.current !== null) clearTimeout(timer.current);
    timer.current = setTimeout(() => setPressed(null), 150);
  }, []);
  return { pressed, touch };
}

/** Шапка игры: название и уровень, очки и серия чипами, справа — слот таймера/раундов/ходов. */
export function GameHeader(props: {
  title: string;
  level: number;
  score: number;
  combo: string;
  right?: ComponentChild;
  chips?: ComponentChild;
}): VNode {
  return (
    <header class="game-header">
      <div class="gh-top">
        <span class="gh-title">{props.title} · ур. {props.level}</span>
        <span class="gh-right">{props.right}</span>
      </div>
      <div class="gh-stats">
        {props.chips}
        <span class="chip">Очки {props.score}</span>
        <span class="chip">Серия {props.combo}</span>
      </div>
    </header>
  );
}

/** Поле: CSS-grid rows×cols квадратных клеток; размер подбирается по ширине зоны
 *  и остатку высоты (tz-m3 §1.3), при нехватке высоты — прокрутка зоны, шапка на месте.
 *  children — функция от размера клетки в px: шрифты клеток задаются от него в px
 *  (cq-единицы на самом контейнере не работают — падают на viewport). */
export function Field(props: { rows: number; cols: number; children: (cell: number) => ComponentChild }): VNode {
  const [zone, setZone] = useState<HTMLElement | null>(null);
  const cell = useCellSize(zone, props.rows, props.cols);
  return (
    <div class="field-scroll" ref={setZone}>
      <div class="field" style={{ gridTemplateColumns: `repeat(${props.cols}, ${cell}px)` }}>
        {props.children(cell)}
      </div>
    </div>
  );
}

/** Подсказка фазы (view.hint) под полем; текст — HTML-подмножество с сервера. */
export function Hint(props: { text?: string }): VNode {
  return <div class="game-hint">{props.text === undefined ? null : renderTelegramHtml(props.text)}</div>;
}

/** «Закончить»: подпись берётся из screen.rows — кнопка с data == actions.quit (tz-m3 §1.2). */
export function QuitButton(props: { screen: Screen; quit: string; press: (payload: string) => void }): VNode | null {
  const button = props.screen.rows.flat().find((b) => b.data === props.quit);
  if (button === undefined) return null;
  return (
    <button type="button" class="btn quit" data-payload={button.data}
            onClick={() => props.press(button.data)}>
      {button.text}
    </button>
  );
}

/** Вибрация сверх каркаса (tz-m3 §1.4): success при переходе кадра в done, error при новой
 *  wrong-клетке, когда note пуст (с note каркас уже провибрировал сам). */
export function useFrameVibration(tg: TelegramWebApp | null, done: boolean, wrongCount: number, note: string | null): void {
  const prev = useRef({ done: false, wrong: 0 });
  useEffect(() => {
    const before = prev.current;
    prev.current = { done, wrong: wrongCount };
    if (done && !before.done) tg?.HapticFeedback.notificationOccurred("success");
    else if (wrongCount > before.wrong && note === null) tg?.HapticFeedback.notificationOccurred("error");
  }, [tg, done, wrongCount, note]);
}

/** Сколько в поле клеток вида kind. */
export function countKind(rows: { k: string }[][]): (kind: string) => number {
  const counts = new Map<string, number>();
  for (const row of rows) {
    for (const cell of row) counts.set(cell.k, (counts.get(cell.k) ?? 0) + 1);
  }
  return (kind) => counts.get(kind) ?? 0;
}

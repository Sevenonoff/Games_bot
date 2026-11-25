// Проложи дорогу (tz-m3 §5): показ с человеком/домом/препятствиями, ввод по линии из
// step-клеток (SVG между соседними), разбор с пунктиром кратчайшей. Что скрыто на вводе —
// клиент не помнит: рендерится только то, что есть в кадре.
import type { VNode } from "preact";
import type { GameProps } from "../registry";
import type { PathCell, PathView } from "../../protocol";
import {
  Field, GameHeader, Hint, QuitButton, countKind, tapPayload, useFrameVibration, usePressed,
} from "../common/parts";
import "./Path.css";

/** Сторона клетки-соседства в px — как gap сетки в common.css. */
const GAP = 4;

/** Отрезки между центрами соседних клеток дороги, координаты в px поля
 *  (центр клетки c: c * (cell + GAP) + cell / 2). В done дорога читается от человека
 *  до дома: концы дороги входят в построение отрезков. */
function segments(mask: boolean[][], cell: number): number[][] {
  const step = cell + GAP;
  const segs: number[][] = [];
  for (let r = 0; r < mask.length; r++) {
    for (let c = 0; c < mask[r].length; c++) {
      if (!mask[r][c]) continue;
      if (mask[r][c + 1]) segs.push([c * step + cell / 2, r * step + cell / 2, (c + 1) * step + cell / 2, r * step + cell / 2]);
      if (mask[r + 1]?.[c]) segs.push([c * step + cell / 2, r * step + cell / 2, c * step + cell / 2, (r + 1) * step + cell / 2]);
    }
  }
  return segs;
}

function maskOf(view: PathView, kinds: PathCell["k"][]): boolean[][] {
  return view.grid.cells.map((row) => row.map((cell) => kinds.includes(cell.k)));
}

export function Path(props: GameProps<PathView>): VNode {
  const { view } = props;
  const { pressed, touch } = usePressed();
  useFrameVibration(props.tg, view.phase === "done", countKind(view.grid.cells)("wrong"), props.note);

  // на review/done любая клетка шлёт skip; иначе tap с координатами (tz-m3 §1.2)
  const payloadFor = (r: number, c: number) =>
    view.phase === "review" || view.phase === "done"
      ? view.actions.skip
      : tapPayload(view.actions.tap, r, c);

  return (
    <div class="game game-path" data-phase={view.phase}>
      <GameHeader
        title={view.title}
        level={view.level}
        score={view.score}
        combo={view.combo}
        right={<span>Раунд {view.rounds?.current ?? 1} из {view.rounds?.total ?? 1}</span>}
      />
      <Field rows={view.grid.rows} cols={view.grid.cols}>
        {(cellPx) => {
          const roadMask = view.phase === "done"
            ? maskOf(view, ["step", "person", "house"])   // итог: дорога от человека до дома
            : maskOf(view, ["step"]);
          const answerMask = maskOf(view, ["answer"]);
          const width = view.grid.cols * cellPx + (view.grid.cols - 1) * GAP;
          const height = view.grid.rows * cellPx + (view.grid.rows - 1) * GAP;
          return [
            ...view.grid.cells.map((row, r) => row.map((cell: PathCell, c) => (
              <button
                key={`${r}:${c}`}
                type="button"
                class={`gcell pt k-${cell.k}${pressed === `${r}:${c}` ? " pressed" : ""}`}
                data-payload={payloadFor(r, c)}
                onClick={() => {
                  touch(`${r}:${c}`);
                  props.press(payloadFor(r, c));
                }}
              >
                {cell.k === "wrong"
                  ? <span style={{ fontSize: Math.round(cellPx * 0.45) }}>❌</span>
                  : <span style={{ fontSize: Math.round(cellPx * 0.55) }}>
                    {cell.k === "person" || cell.k === "house" ? cell.v
                      : cell.k === "step" ? "●"
                        : cell.k === "block" ? "⛔" : null}
                  </span>}
              </button>
            ))),
            // размер — ровно с сеткой в px: растягивание родителем и viewBox без gap
            // рисовали линии мимо клеток (приёмка M3-1)
            <svg key="lines" class="path-lines" width={width} height={height}
                 viewBox={`0 0 ${width} ${height}`}
                 style={{
                   "--ln-step": `${Math.max(3, cellPx * 0.16).toFixed(1)}px`,
                   "--ln-answer": `${Math.max(3, cellPx * 0.14).toFixed(1)}px`,
                   "--ln-dash": `${(cellPx * 0.24).toFixed(1)}px ${(cellPx * 0.18).toFixed(1)}px`,
                 }}>
              {answerMask && segments(answerMask, cellPx).map((s, i) => (
                <line key={`a${i}`} class="ln-answer" x1={s[0]} y1={s[1]} x2={s[2]} y2={s[3]} />
              ))}
              {segments(roadMask, cellPx).map((s, i) => (
                <line key={`s${i}`} class="ln-step" x1={s[0]} y1={s[1]} x2={s[2]} y2={s[3]} />
              ))}
            </svg>,
            view.phase === "countdown"
              ? <div key="cd" class="countdown-overlay" style={{ fontSize: Math.round(cellPx * 1.4) }}>{view.countdown}</div>
              : null,
          ];
        }}
      </Field>
      <Hint text={view.hint} />
      <QuitButton screen={props.screen} quit={view.actions.quit} press={props.press} />
    </div>
  );
}

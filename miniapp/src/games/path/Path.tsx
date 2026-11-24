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

/** Отрезки между центрами соседних клеток — по ним рисуется линия дороги. */
function segments(cells: boolean[][]): number[][] {
  const segs: number[][] = [];
  for (let r = 0; r < cells.length; r++) {
    for (let c = 0; c < cells[r].length; c++) {
      if (!cells[r][c]) continue;
      if (cells[r][c + 1]) segs.push([c + 0.5, r + 0.5, c + 1.5, r + 0.5]);
      if (cells[r + 1]?.[c]) segs.push([c + 0.5, r + 0.5, c + 0.5, r + 1.5]);
    }
  }
  return segs;
}

function maskOf(view: PathView, kind: PathCell["k"]): boolean[][] {
  return view.grid.cells.map((row) => row.map((cell) => cell.k === kind));
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

  const stepSegs = segments(maskOf(view, "step"));
  const answerSegs = segments(maskOf(view, "answer"));

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
        {(cellPx) => [
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
          <svg key="lines" class="path-lines" viewBox={`0 0 ${view.grid.cols} ${view.grid.rows}`} preserveAspectRatio="none">
            {answerSegs.map((s, i) => (
              <line key={`a${i}`} class="ln-answer" x1={s[0]} y1={s[1]} x2={s[2]} y2={s[3]} />
            ))}
            {stepSegs.map((s, i) => (
              <line key={`s${i}`} class="ln-step" x1={s[0]} y1={s[1]} x2={s[2]} y2={s[3]} />
            ))}
          </svg>,
          view.phase === "countdown"
            ? <div key="cd" class="countdown-overlay" style={{ fontSize: Math.round(cellPx * 1.4) }}>{view.countdown}</div>
            : null,
        ]}
      </Field>
      <Hint text={view.hint} />
      <QuitButton screen={props.screen} quit={view.actions.quit} press={props.press} />
    </div>
  );
}

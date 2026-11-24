// Матрица памяти (tz-m3 §3): фазы countdown/preview/input/review/done, полоска таймера
// с плавным ходом между кадрами, синие/зелёные/красные клетки. Всё поле — из кадра сервера.
import type { VNode } from "preact";
import type { GameProps } from "../registry";
import type { MatrixView } from "../../protocol";
import { TimerBar } from "../common/TimerBar";
import {
  Field, GameHeader, Hint, QuitButton, countKind, tapPayload, useFrameVibration, usePressed,
} from "../common/parts";
import "./Matrix.css";

export function Matrix(props: GameProps<MatrixView>): VNode {
  const { view } = props;
  const { pressed, touch } = usePressed();
  useFrameVibration(props.tg, view.phase === "done", countKind(view.grid.cells)("wrong"), props.note);

  // на review/done любая клетка шлёт skip; иначе tap с координатами (tz-m3 §1.2)
  const payloadFor = (r: number, c: number) =>
    view.phase === "review" || view.phase === "done"
      ? view.actions.skip
      : tapPayload(view.actions.tap, r, c);

  return (
    <div class="game game-matrix" data-phase={view.phase}>
      <GameHeader
        title={view.title}
        level={view.level}
        score={view.score}
        combo={view.combo}
        right={<span class={view.timer.overtime ? "over" : ""}>
          {view.timer.overtime ? "Время вышло" : `⏱ ${view.timer.left} с`}
        </span>}
      />
      <TimerBar left={view.timer.left} total={view.timer.total} overtime={view.timer.overtime} />
      <Field rows={view.grid.rows} cols={view.grid.cols}>
        {(cellPx) => [
          ...view.grid.cells.map((row, r) => row.map((cell, c) => (
            <button
              key={`${r}:${c}`}
              type="button"
              class={`gcell mx k-${cell.k}${pressed === `${r}:${c}` ? " pressed" : ""}`}
              data-payload={payloadFor(r, c)}
              onClick={() => {
                touch(`${r}:${c}`);
                props.press(payloadFor(r, c));
              }}
            >
              {cell.k === "wrong" ? <span style={{ fontSize: Math.round(cellPx * 0.5) }}>❌</span> : null}
            </button>
          ))),
          view.phase === "countdown"
            ? <div class="countdown-overlay" style={{ fontSize: Math.round(cellPx * 1.4) }}>{view.countdown}</div>
            : null,
        ]}
      </Field>
      <Hint text={view.hint} />
      <QuitButton screen={props.screen} quit={view.actions.quit} press={props.press} />
    </div>
  );
}

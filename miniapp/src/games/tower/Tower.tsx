// Поездка на числах (tz-m3 §4): жёлтые неактивные, белые с числами, дорога с машинкой
// над полем (extra.road / extra.km), «Раунд N из M». Поле — из кадра сервера.
import type { VNode } from "preact";
import type { GameProps } from "../registry";
import type { TowerCell, TowerView } from "../../protocol";
import {
  Field, GameHeader, Hint, QuitButton, countKind, tapPayload, useFrameVibration, usePressed,
} from "../common/parts";
import "./Tower.css";

export function Tower(props: GameProps<TowerView>): VNode {
  const { view } = props;
  const { pressed, touch } = usePressed();
  useFrameVibration(props.tg, view.phase === "done", countKind(view.grid.cells)("wrong"), props.note);

  // на review/done любая клетка шлёт skip; иначе tap с координатами (tz-m3 §1.2)
  const payloadFor = (r: number, c: number) =>
    view.phase === "review" || view.phase === "done"
      ? view.actions.skip
      : tapPayload(view.actions.tap, r, c);

  return (
    <div class="game game-tower" data-phase={view.phase}>
      <GameHeader
        title={view.title}
        level={view.level}
        score={view.score}
        combo={view.combo}
        right={<span>Раунд {view.rounds?.current ?? 1} из {view.rounds?.total ?? 1}</span>}
      />
      <div class="road" aria-hidden="true">
        <span class="road-finish">🏁</span>
        <span class="road-car" style={{ right: `${Math.round(Math.min(1, Math.max(0, view.extra.road)) * 100)}%` }}>🚗</span>
      </div>
      <div class="road-km">Проехали {view.extra.km} км</div>
      <Field rows={view.grid.rows} cols={view.grid.cols}>
        {(cellPx) => [
          ...view.grid.cells.map((row, r) => row.map((cell: TowerCell, c) => (
            <button
              key={`${r}:${c}`}
              type="button"
              class={`gcell tw k-${cell.k}${pressed === `${r}:${c}` ? " pressed" : ""}`}
              data-payload={payloadFor(r, c)}
              onClick={() => {
                touch(`${r}:${c}`);
                props.press(payloadFor(r, c));
              }}
            >
              {cell.k === "wrong"
                ? <span class="wrong-mark" style={{ fontSize: Math.round(cellPx * 0.5) }}>❌</span>
                : (cell.k === "number" ? <span style={{ fontSize: Math.round(cellPx * 0.44) }}>{cell.v}</span> : null)}
              {cell.k === "wrong" && cell.v !== undefined
                ? <span class="wrong-num" style={{ fontSize: Math.round(cellPx * 0.28) }}>{cell.v}</span>
                : null}
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

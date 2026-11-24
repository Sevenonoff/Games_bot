// Мемо (tz-m3 §2): карты рубашкой вверх, переворот по оси Y, найденные бледнеют,
// собранное поле подпрыгивает. Поле и счёт — только из кадра сервера.
import type { VNode } from "preact";
import type { GameProps } from "../registry";
import type { MemoCell, MemoView } from "../../protocol";
import { Field, GameHeader, Hint, QuitButton, tapPayload, useFrameVibration, usePressed } from "../common/parts";
import "./Memo.css";

export function Memo(props: GameProps<MemoView>): VNode {
  const { view } = props;
  const { pressed, touch } = usePressed();
  useFrameVibration(props.tg, view.done, 0, props.note);   // у мемо wrong-клеток нет

  // на done любая карта шлёт skip; иначе — tap с координатами (tz-m3 §1.2)
  const payloadFor = (r: number, c: number) =>
    view.done ? view.actions.skip : tapPayload(view.actions.tap, r, c);

  return (
    <div class="game game-memo" data-phase={view.done ? "done" : "play"}>
      <GameHeader
        title={view.title}
        level={view.level}
        score={view.score}
        combo={view.combo}
        right={<span class={view.moves.made > view.moves.limit ? "over" : ""}>
          Ходы {view.moves.made} из {view.moves.limit}
        </span>}
        chips={<span class="chip">Пары {view.pairs.found}/{view.pairs.total}</span>}
      />
      <Field rows={view.grid.rows} cols={view.grid.cols}>
        {(cell) => view.grid.cells.map((row, r) => row.map((card: MemoCell, c) => (
          <button
            key={`${r}:${c}`}
            type="button"
            class={`gcell card k-${card.k}${pressed === `${r}:${c}` ? " pressed" : ""}`}
            data-payload={payloadFor(r, c)}
            onClick={() => {
              touch(`${r}:${c}`);
              props.press(payloadFor(r, c));
            }}
          >
            <span class="card-inner">
              <span class="card-side card-front" style={{ fontSize: Math.round(cell * 0.6) }}>
                {card.k === "back" ? "" : card.v}
              </span>
              <span class="card-side card-back" />
            </span>
          </button>
        )))}
      </Field>
      <Hint text={view.hint} />
      <QuitButton screen={props.screen} quit={view.actions.quit} press={props.press} />
    </div>
  );
}

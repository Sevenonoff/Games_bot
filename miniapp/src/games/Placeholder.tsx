// Заглушка для view.kind без компонента: универсальный рендер + плашка «скоро».
// Каркас показывает её, пока игры M3/M4 не добавят свои компоненты в registry.
import type { VNode } from "preact";
import { GenericScreen } from "../app/GenericScreen";
import type { View } from "../protocol";
import type { GameProps } from "./registry";

export function Placeholder(props: GameProps<View>): VNode {
  return (
    <div class="placeholder">
      <div class="soon" role="note">✨ Красивый экран игры — скоро</div>
      <GenericScreen screen={props.screen} press={props.press} />
    </div>
  );
}

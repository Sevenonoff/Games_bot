// Полоска таймера партии матрицы (tz-m3 §3): во всю ширину, красная при ≤ 10 с.
// Кадры с таймером приходят раз в 5 с — между ними полоска уменьшается сама:
// при новом left ширина ставится без перехода и переводится в 0 за left секунд
// (CSS transition, без перерисовки компонента). Число секунд показывает шапка.
import type { VNode } from "preact";
import { useEffect, useRef } from "preact/hooks";

export function TimerBar(props: { left: number; total: number; overtime: boolean }): VNode {
  const fill = useRef<HTMLDivElement | null>(null);
  const from = Math.max(0, props.left);

  useEffect(() => {
    const el = fill.current;
    if (el === null || props.overtime || from === 0) {
      if (el !== null) {
        el.style.transition = "none";
        el.style.width = "0%";
      }
      return;
    }
    el.style.transition = "none";
    el.style.width = `${(from / props.total) * 100}%`;
    void el.offsetWidth;                        // применить ширину без перехода
    el.style.transition = `width ${from}s linear`;
    el.style.width = "0%";
  }, [from, props.overtime, props.total]);

  return (
    <div class={"timerbar" + (from <= 10 || props.overtime ? " low" : "")} role="timer">
      <div class="timerbar-fill" ref={fill} />
    </div>
  );
}

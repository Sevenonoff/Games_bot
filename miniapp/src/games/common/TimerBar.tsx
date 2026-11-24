// Полоска таймера партии матрицы (tz-m3 §3): во всю ширину, красная при ≤ 10 с.
// Кадры с таймером приходят раз в 5 с — между ними клиент плавно уменьшает полоску сам
// от последнего left; число секунд показывает только из кадра (в шапке, не здесь).
import type { VNode } from "preact";
import { useEffect, useRef, useState } from "preact/hooks";

export function TimerBar(props: { left: number; total: number; overtime: boolean }): VNode {
  const from = Math.max(0, props.left);
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    setElapsed(0);
    const startedAt = performance.now();
    let raf = 0;
    const tick = () => {
      setElapsed((performance.now() - startedAt) / 1000);
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [from]);

  const localLeft = Math.max(0, from - elapsed);
  const frac = props.overtime ? 0 : Math.min(1, localLeft / props.total);
  return (
    <div class={"timerbar" + (from <= 10 || props.overtime ? " low" : "")} role="timer">
      <div class="timerbar-fill" style={{ width: `${frac * 100}%` }} />
    </div>
  );
}

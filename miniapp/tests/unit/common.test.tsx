// Общие части игр (tz-m3 §1.1): подстановка {r}/{c}, шапка, поле, «Закончить».
import { cleanup, render } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";
import type { VNode } from "preact";
import { Field, GameHeader, QuitButton, tapPayload, useFrameVibration } from "../../src/games/common/parts";

afterEach(cleanup);

describe("tapPayload", () => {
  it("подставляет {r} и {c} в шаблон actions.tap", () => {
    expect(tapPayload("t:a1b2c3:{r}:{c}", 2, 4)).toBe("t:a1b2c3:2:4");
    expect(tapPayload("mpf:ABC:{r}:{c}", 0, 0)).toBe("mpf:ABC:0:0");
  });
});

describe("GameHeader", () => {
  it("показывает название с уровнем, очки, серию и правый слот", () => {
    const { container } = render(
      <GameHeader title="🃏 Мемо" level={5} score={120} combo="×2" right={<span>справа</span>} />,
    );
    expect(container.querySelector(".gh-title")!.textContent).toContain("ур. 5");
    expect(container.querySelector(".gh-stats")!.textContent).toContain("Очки 120");
    expect(container.querySelector(".gh-stats")!.textContent).toContain("Серия ×2");
    expect(container.querySelector(".gh-right")!.textContent).toBe("справа");
  });
});

describe("Field", () => {
  it("сетка по cols, клетки-потомки получают размер клетки", () => {
    const { container } = render(
      <Field rows={2} cols={3}>
        {(cell) => [<button class="gcell" type="button" style={{ fontSize: cell }}>1</button>,
          <button class="gcell" type="button">2</button>]}
      </Field>,
    );
    const field = container.querySelector<HTMLElement>(".field")!;
    expect(field.getAttribute("style")).toContain("repeat(3,");
    expect(field.querySelectorAll(".gcell")).toHaveLength(2);
    expect(container.querySelector(".gcell")).not.toBeNull();
  });
});

describe("QuitButton", () => {
  it("находит кнопку экрана с data == quit и жмёт её", () => {
    const press = vi.fn();
    const screen = {
      text: "", image: null, view: null,
      rows: [[{ text: "🏁 Закончить", data: "q:a1b2c3" }], [{ text: "🏠 Меню", data: "menu" }]],
    };
    const { container } = render(<QuitButton screen={screen} quit="q:a1b2c3" press={press} />);
    const quit = container.querySelector<HTMLButtonElement>("button.quit")!;
    expect(quit.textContent).toContain("Закончить");
    quit.click();
    expect(press).toHaveBeenCalledWith("q:a1b2c3");
  });

  it("нет такой кнопки — не рисуется", () => {
    const screen = { text: "", image: null, view: null, rows: [[{ text: "🏠 Меню", data: "menu" }]] };
    const { container } = render(<QuitButton screen={screen} quit="q:zzz" press={vi.fn()} />);
    expect(container.querySelector("button.quit")).toBeNull();
  });
});

// Вибрация кадров (tz-m3 §1.4): прямой тест хука через обёртку.
import type { TelegramWebApp } from "../../src/telegram";

function VibeProbe(props: { tg: TelegramWebApp | null; done: boolean; wrong: number; note: string | null }): VNode {
  useFrameVibration(props.tg, props.done, props.wrong, props.note);
  return <div />;
}

function fakeTg() {
  const haptics: string[] = [];
  const tg: TelegramWebApp = {
    initData: "", initDataUnsafe: {}, themeParams: {}, ready() {}, expand() {}, onEvent() {},
    showConfirm: () => {}, openTelegramLink: () => {},
    BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
    HapticFeedback: {
      selectionChanged() {},
      notificationOccurred: (t) => { haptics.push(`notify:${t}`); },
      impactOccurred: (s) => { haptics.push(`impact:${s}`); },
    },
  };
  return { tg, haptics };
}

describe("useFrameVibration", () => {
  it("первый кадр сразу done/review — вибраций нет (открытие посреди партии)", () => {
    const { tg, haptics } = fakeTg();
    const view = render(<VibeProbe tg={tg} done={true} wrong={2} note={null} />);
    expect(haptics).toEqual([]);
    view.rerender(<VibeProbe tg={tg} done={true} wrong={2} note={null} />);
    expect(haptics).toEqual([]);            // кадр без изменений — тоже тишина
  });

  it("wrong появилась в кадре С note — вибраций нет (каркас уже провибрировал)", () => {
    const { tg, haptics } = fakeTg();
    const view = render(<VibeProbe tg={tg} done={false} wrong={0} note={null} />);
    view.rerender(<VibeProbe tg={tg} done={false} wrong={1} note="❌ Ошибка. На поле — правильный ответ" />);
    expect(haptics).toEqual([]);
  });

  it("wrong появилась БЕЗ note — error; потом done — success", () => {
    const { tg, haptics } = fakeTg();
    const view = render(<VibeProbe tg={tg} done={false} wrong={0} note={null} />);
    view.rerender(<VibeProbe tg={tg} done={false} wrong={1} note={null} />);
    expect(haptics).toEqual(["notify:error"]);
    view.rerender(<VibeProbe tg={tg} done={true} wrong={1} note={null} />);
    expect(haptics).toEqual(["notify:error", "notify:success"]);
  });
});

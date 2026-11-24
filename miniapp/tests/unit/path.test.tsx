// Проложи дорогу (tz-m3 §7.2): образцы фаз, линии SVG, скрытие препятствий на вводе,
// payload'ы, вибрация.
import { cleanup, fireEvent, render } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Path } from "../../src/games/path/Path";
import type { GameProps } from "../../src/games/registry";
import type { PathView, Screen } from "../../src/protocol";
import type { TelegramWebApp } from "../../src/telegram";
import countdown from "../../../docs/miniapp/fixtures/path-countdown.json";
import preview from "../../../docs/miniapp/fixtures/path-preview.json";
import input from "../../../docs/miniapp/fixtures/path-input.json";
import review from "../../../docs/miniapp/fixtures/path-review.json";
import done from "../../../docs/miniapp/fixtures/path-done.json";

afterEach(cleanup);

const FIXTURES = { countdown, preview, input, review, done };
type FixtureName = keyof typeof FIXTURES;

function fakeTg() {
  const haptics: string[] = [];
  const tg: TelegramWebApp = {
    initData: "", initDataUnsafe: {}, themeParams: {}, ready() {}, expand() {},
    onEvent() {},
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

function props(name: FixtureName, over: Partial<GameProps<PathView>> = {}): GameProps<PathView> {
  const screen = FIXTURES[name] as unknown as Screen;
  return { view: screen.view as PathView, screen, press: vi.fn(), note: null, tg: null, ...over };
}

describe("Дорога: образцы всех фаз", () => {
  for (const name of Object.keys(FIXTURES) as FixtureName[]) {
    it(`фикстура path-${name} рендерится`, () => {
      const { container } = render(<Path {...props(name)} />);
      const game = container.querySelector(".game-path");
      expect(game).not.toBeNull();
      expect(game!.getAttribute("data-phase")).toBe(name);
      expect(game!.querySelectorAll(".gcell").length).toBeGreaterThan(0);
      expect(container.firstElementChild).toMatchSnapshot(`path-${name}: DOM`);
    });
  }
});

describe("Дорога: показ и скрытие", () => {
  it("на preview видны человек, дом и препятствия", () => {
    const { container } = render(<Path {...props("preview")} />);
    expect(container.querySelector(".k-person")?.textContent).toContain("🏃");
    expect(container.querySelector(".k-house")?.textContent).toContain("🏡");
    expect(container.querySelectorAll(".k-block").length).toBeGreaterThan(0);
  });

  it("на input препятствий и концов нет — только пустые клетки и дорога игрока", () => {
    const { container } = render(<Path {...props("input")} />);
    expect(container.querySelectorAll(".k-block").length).toBe(0);
    expect(container.querySelectorAll(".k-person").length).toBe(0);
    expect(container.querySelectorAll(".k-house").length).toBe(0);
    expect(container.querySelectorAll(".k-step").length).toBeGreaterThan(0);
  });

  it("одиночная step-клетка без соседей — линия не рисуется", () => {
    const { container } = render(<Path {...props("input")} />);
    expect(container.querySelectorAll(".k-step")).toHaveLength(1);
    expect(container.querySelectorAll(".ln-step")).toHaveLength(0);
  });

  it("на review есть пунктир кратчайшей и ❌ на ошибке", () => {
    const { container } = render(<Path {...props("review")} />);
    expect(container.querySelectorAll(".ln-answer").length).toBeGreaterThan(0);
    expect(container.querySelector(".k-wrong")?.textContent).toContain("❌");
  });

  it("на done поле открыто, дорога игрока сплошной линией", () => {
    const { container } = render(<Path {...props("done")} />);
    expect(container.querySelectorAll(".k-block").length).toBeGreaterThan(0);
    expect(container.querySelectorAll(".ln-step").length).toBeGreaterThan(0);
  });
});

describe("Дорога: нажатия", () => {
  it("в input клетка шлёт tap; на review/done — skip", () => {
    const p = props("input");
    const { container } = render(<Path {...p} />);
    fireEvent.click(container.querySelectorAll(".gcell")[0]!);
    expect(p.press).toHaveBeenCalledWith("t:a1b2c3:0:0");

    cleanup();
    const pDone = props("done");
    const second = render(<Path {...pDone} />);
    const cells = second.container.querySelectorAll<HTMLButtonElement>(".gcell");
    for (const cell of cells) expect(cell.dataset.payload).toBe("t:a1b2c3:0:0");
    fireEvent.click(cells[0]!);
    expect(pDone.press).toHaveBeenCalledWith("t:a1b2c3:0:0");
  });

  it("«Закончить» шлёт quit", () => {
    const p = props("input");
    const { container } = render(<Path {...p} />);
    fireEvent.click(container.querySelector("button.quit")!);
    expect(p.press).toHaveBeenCalledWith("q:a1b2c3");
  });
});

describe("Дорога: вибрация", () => {
  it("переход в done — success; новая wrong без note — error", () => {
    const { tg, haptics } = fakeTg();
    const view = render(<Path {...props("input", { tg })} />);
    view.rerender(<Path {...props("review", { tg })} />);
    expect(haptics).toEqual(["notify:error"]);
    view.rerender(<Path {...props("done", { tg })} />);
    expect(haptics).toEqual(["notify:error", "notify:success"]);
  });
});

// Матрица памяти (tz-m3 §7.2): образцы всех фаз, payload'ы по фазам, таймер, вибрация.
import { cleanup, fireEvent, render } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Matrix } from "../../src/games/matrix/Matrix";
import type { GameProps } from "../../src/games/registry";
import type { MatrixView, Screen } from "../../src/protocol";
import type { TelegramWebApp } from "../../src/telegram";
import countdown from "../../../docs/miniapp/fixtures/matrix-countdown.json";
import preview from "../../../docs/miniapp/fixtures/matrix-preview.json";
import input from "../../../docs/miniapp/fixtures/matrix-input.json";
import review from "../../../docs/miniapp/fixtures/matrix-review.json";
import done from "../../../docs/miniapp/fixtures/matrix-done.json";

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

function props(name: FixtureName, over: Partial<GameProps<MatrixView>> = {}): GameProps<MatrixView> {
  const screen = FIXTURES[name] as unknown as Screen;
  return { view: screen.view as MatrixView, screen, press: vi.fn(), note: null, tg: null, ...over };
}

describe("Матрица: образцы всех фаз", () => {
  for (const name of Object.keys(FIXTURES) as FixtureName[]) {
    it(`фикстура matrix-${name} рендерится`, () => {
      const { container } = render(<Matrix {...props(name)} />);
      const game = container.querySelector(".game-matrix");
      expect(game).not.toBeNull();
      expect(game!.getAttribute("data-phase")).toBe(name === "done" ? "done" : name);
      expect(game!.querySelectorAll(".gcell").length).toBeGreaterThan(0);
      expect(container.firstElementChild).toMatchSnapshot(`matrix-${name}: DOM`);
    });
  }
});

describe("Матрица: нажатия и таймер", () => {
  it("в input клетка шлёт tap, на review/done — skip", () => {
    const p = props("input");
    const { container } = render(<Matrix {...p} />);
    fireEvent.click(container.querySelectorAll(".gcell")[0]!);
    expect(p.press).toHaveBeenCalledWith("t:a1b2c3:0:0");
  });

  it("на done любая клетка шлёт skip", () => {
    const p = props("done");
    const { container } = render(<Matrix {...p} />);
    const cells = container.querySelectorAll<HTMLButtonElement>(".gcell");
    for (const cell of cells) expect(cell.dataset.payload).toBe("t:a1b2c3:0:0");
    fireEvent.click(cells[0]!);
    expect(p.press).toHaveBeenCalledWith("t:a1b2c3:0:0");
  });

  it("полоска таймера: ширина из кадра, число секунд в шапке", () => {
    const { container } = render(<Matrix {...props("input")} />);
    expect(container.querySelector(".gh-right")!.textContent).toContain("60");
    const fill = container.querySelector<HTMLElement>(".timerbar-fill")!;
    expect(fill.style.width).toBe("100%");
    expect(container.querySelector(".timerbar")!.classList).not.toContain("low");
  });

  it("«Закончить» шлёт quit", () => {
    const p = props("input");
    const { container } = render(<Matrix {...p} />);
    fireEvent.click(container.querySelector("button.quit")!);
    expect(p.press).toHaveBeenCalledWith("q:a1b2c3");
  });
});

describe("Матрица: вибрация", () => {
  it("переход фазы в done — success", () => {
    const { tg, haptics } = fakeTg();
    const view = render(<Matrix {...props("input", { tg })} />);
    view.rerender(<Matrix {...props("done", { tg })} />);
    expect(haptics).toEqual(["notify:success"]);
  });

  it("новая wrong без note — error; с note каркас уже провибрировал — молчим", () => {
    const { tg, haptics } = fakeTg();
    const view = render(<Matrix {...props("input", { tg })} />);
    view.rerender(<Matrix {...props("review", { tg })} />);          // wrong появилась, note нет
    expect(haptics).toEqual(["notify:error"]);
    view.rerender(<Matrix {...props("review", { tg, note: "❌ Ошибка" })} />);
    expect(haptics).toEqual(["notify:error"]);
  });
});

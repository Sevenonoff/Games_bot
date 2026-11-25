// Поездка на числах (tz-m3 §7.2): образцы фаз, дорога и км, payload'ы, вибрация.
import { cleanup, fireEvent, render } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Tower } from "../../src/games/tower/Tower";
import type { GameProps } from "../../src/games/registry";
import type { Screen, TowerView } from "../../src/protocol";
import type { TelegramWebApp } from "../../src/telegram";
import countdown from "../../../docs/miniapp/fixtures/tower-countdown.json";
import preview from "../../../docs/miniapp/fixtures/tower-preview.json";
import input from "../../../docs/miniapp/fixtures/tower-input.json";
import review from "../../../docs/miniapp/fixtures/tower-review.json";

afterEach(cleanup);

const FIXTURES = { countdown, preview, input, review };
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

function props(name: FixtureName, over: Partial<GameProps<TowerView>> = {}): GameProps<TowerView> {
  const screen = FIXTURES[name] as unknown as Screen;
  return { view: screen.view as TowerView, screen, press: vi.fn(), note: null, tg: null, ...over };
}

describe("Поездка: образцы всех фаз", () => {
  for (const name of Object.keys(FIXTURES) as FixtureName[]) {
    it(`фикстура tower-${name} рендерится`, () => {
      const { container } = render(<Tower {...props(name)} />);
      const game = container.querySelector(".game-tower");
      expect(game).not.toBeNull();
      expect(game!.getAttribute("data-phase")).toBe(name);
      expect(game!.querySelectorAll(".gcell").length).toBeGreaterThan(0);
      expect(container.firstElementChild).toMatchSnapshot(`tower-${name}: DOM`);
    });
  }
});

describe("Поездка: дорога и раунды", () => {
  it("машинка стоит по extra.road, под дорогой — пройденные км", () => {
    const { container } = render(<Tower {...props("input")} />);
    expect(container.querySelector<HTMLElement>(".road-car")!.style.right).toBe("3%");   // старт справа
    expect(container.querySelector(".road-km")!.textContent).toContain("Проехали 10 км");
    expect(container.querySelector(".gh-right")!.textContent).toContain("Раунд 1 из 6");
  });

  it("финиш слева, машинка справа налево", () => {
    const { container } = render(<Tower {...props("preview")} />);
    expect(container.querySelector(".road-finish")!.textContent).toBe("🏁");
    expect(container.querySelector<HTMLElement>(".road-car")!.style.right).toBe("0%");   // road 0 — машинка справа
  });
});

describe("Поездка: нажатия", () => {
  it("в input клетка шлёт tap; на review — skip", () => {
    const pIn = props("input");
    const { container } = render(<Tower {...pIn} />);
    fireEvent.click(container.querySelectorAll(".gcell")[0]!);
    expect(pIn.press).toHaveBeenCalledWith("t:a1b2c3:0:0");

    cleanup();
    const pRev = props("review");
    const second = render(<Tower {...pRev} />);
    const cells = second.container.querySelectorAll<HTMLButtonElement>(".gcell");
    for (const cell of cells) expect(cell.dataset.payload).toBe("t:a1b2c3:0:0");
    fireEvent.click(cells[0]!);
    expect(pRev.press).toHaveBeenCalledWith("t:a1b2c3:0:0");
  });

  it("«Закончить» шлёт quit", () => {
    const p = props("input");
    const { container } = render(<Tower {...p} />);
    fireEvent.click(container.querySelector("button.quit")!);
    expect(p.press).toHaveBeenCalledWith("q:a1b2c3");
  });

  it("wrong показывает правильное число в углу", () => {
    const { container } = render(<Tower {...props("review")} />);
    expect(container.querySelector(".wrong-num")?.textContent).toMatch(/\d/);
  });
});

describe("Поездка: вибрация", () => {
  it("новая wrong без note — error", () => {
    const { tg, haptics } = fakeTg();
    const view = render(<Tower {...props("input", { tg })} />);
    view.rerender(<Tower {...props("review", { tg })} />);
    expect(haptics).toEqual(["notify:error"]);
  });
});

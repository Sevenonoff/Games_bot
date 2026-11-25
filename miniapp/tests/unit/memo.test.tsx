// Мемо (tz-m3 §7.2): все образцы fixtures рендерятся, снимки DOM, payload'ы из шаблонов,
// «Закончить», вибрация done→success.
import { cleanup, fireEvent, render } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Memo } from "../../src/games/memo/Memo";
import type { GameProps } from "../../src/games/registry";
import type { MemoView, Screen } from "../../src/protocol";
import type { TelegramWebApp } from "../../src/telegram";
import memoPlay from "../../../docs/miniapp/fixtures/memo-play.json";
import memoMismatch from "../../../docs/miniapp/fixtures/memo-mismatch.json";
import memoDone from "../../../docs/miniapp/fixtures/memo-done.json";

afterEach(cleanup);

const FIXTURES = { play: memoPlay, mismatch: memoMismatch, done: memoDone };

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

function props(fixture: keyof typeof FIXTURES, over: Partial<GameProps<MemoView>> = {}): GameProps<MemoView> {
  const screen = FIXTURES[fixture] as unknown as Screen;
  return {
    view: screen.view as MemoView,
    screen,
    press: vi.fn(),
    note: null,
    tg: null,
    ...over,
  };
}

describe("Мемо: образцы", () => {
  for (const name of ["play", "mismatch", "done"] as const) {
    it(`фикстура memo-${name} рендерится и снимок осмысленный`, () => {
      const { container } = render(<Memo {...props(name)} />);
      const game = container.querySelector(".game-memo");
      expect(game).not.toBeNull();
      expect(game!.getAttribute("data-phase")).toMatchSnapshot(`memo-${name}: data-phase`);
      expect(game!.querySelectorAll(".gcell").length).toBeGreaterThan(0);
      expect(container.firstElementChild).toMatchSnapshot(`memo-${name}: DOM`);
    });
  }
});

describe("Мемо: нажатия", () => {
  it("закрытая карта шлёт tap с координатами, открытая — тоже tap", () => {
    const p = props("play");
    const { container } = render(<Memo {...p} />);
    // фикстура: (0,0) — face, (0,1) — back
    const cells = container.querySelectorAll<HTMLButtonElement>(".gcell");
    fireEvent.click(cells[1]!);
    fireEvent.click(cells[0]!);
    expect(p.press).toHaveBeenNthCalledWith(1, "t:a1b2c3:0:1");
    expect(p.press).toHaveBeenNthCalledWith(2, "t:a1b2c3:0:0");
  });

  it("на done любая карта шлёт skip", () => {
    const p = props("done");
    const { container } = render(<Memo {...p} />);
    const cells = container.querySelectorAll<HTMLButtonElement>(".gcell");
    for (const cell of cells) expect(cell.dataset.payload).toBe("t:a1b2c3:0:0");
    fireEvent.click(cells[0]!);
    expect(p.press).toHaveBeenCalledWith("t:a1b2c3:0:0");
  });

  it("«Закончить» — подпись из screen.rows, payload из actions.quit", () => {
    const p = props("play");
    const { container } = render(<Memo {...p} />);
    const quit = container.querySelector<HTMLButtonElement>("button.quit")!;
    expect(quit.textContent).toContain("Закончить");
    fireEvent.click(quit);
    expect(p.press).toHaveBeenCalledWith("q:a1b2c3");
  });

  it("шапка: пары, ходы (красные сверх лимита), очки, серия", () => {
    const { container } = render(<Memo {...props("mismatch")} />);
    expect(container.querySelector(".gh-stats")!.textContent).toContain("Пары 0/3");
    const right = container.querySelector<HTMLElement>(".gh-right")!;
    expect(right.textContent).toContain("Ходы 1 из 6");
    expect(right.classList).not.toContain("over");
  });
});

describe("Мемо: вибрация", () => {
  it("переход в done — success, без дублей на note", () => {
    const { tg, haptics } = fakeTg();
    const base = props("play", { tg });
    const view = render(<Memo {...base} />);
    view.rerender(<Memo {...props("done", { tg })} />);
    expect(haptics).toEqual(["notify:success"]);
    // повторный кадр в done больше не вибрирует
    view.rerender(<Memo {...props("done", { tg, note: "✅" })} />);
    expect(haptics).toEqual(["notify:success"]);
  });
});

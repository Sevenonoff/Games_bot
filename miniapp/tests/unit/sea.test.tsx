// Морской бой (tz-m4 §8.2): образцы fixtures, выстрел, неактивные поля, кнопки из
// screen.rows, перетаскивание (place с центром по ядру), fix после current, showConfirm,
// вибрация по разнице кадров.
import { act, cleanup, fireEvent, render } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";
import { Sea } from "../../src/games/sea/Sea";
import type { GameProps } from "../../src/games/registry";
import type { Screen, SeaView } from "../../src/protocol";
import type { TelegramWebApp } from "../../src/telegram";
import placement from "../../../docs/miniapp/fixtures/sea-placement.json";
import placementCurrent from "../../../docs/miniapp/fixtures/sea-placement-current.json";
import waitingReady from "../../../docs/miniapp/fixtures/sea-waiting-ready.json";
import invite from "../../../docs/miniapp/fixtures/sea-invite.json";
import myTurn from "../../../docs/miniapp/fixtures/sea-my-turn.json";
import aiThinking from "../../../docs/miniapp/fixtures/sea-ai-thinking.json";
import theirShot from "../../../docs/miniapp/fixtures/sea-their-shot.json";
import blink from "../../../docs/miniapp/fixtures/sea-blink.json";
import result from "../../../docs/miniapp/fixtures/sea-result.json";

afterEach(cleanup);

const FIXTURES = { placement, placementCurrent, waitingReady, invite, myTurn, aiThinking, theirShot, blink, result };
type FixtureName = keyof typeof FIXTURES;

function fakeTg() {
  const haptics: string[] = [];
  const confirms: Array<{ text: string; ok: boolean }> = [];
  const links: string[] = [];
  const tg: TelegramWebApp = {
    initData: "", initDataUnsafe: {}, themeParams: {}, ready() {}, expand() {}, onEvent() {},
    showConfirm: (text, callback) => { confirms.push({ text, ok: true }); callback?.(true); },
    openTelegramLink: (url) => { links.push(url); },
    BackButton: { show() {}, hide() {}, onClick() {}, offClick() {} },
    HapticFeedback: {
      selectionChanged() {},
      notificationOccurred: (t) => { haptics.push(`notify:${t}`); },
      impactOccurred: (s) => { haptics.push(`impact:${s}`); },
    },
  };
  return { tg, haptics, confirms, links };
}

function props(name: FixtureName, over: Partial<GameProps<SeaView>> = {}): GameProps<SeaView> {
  const screen = FIXTURES[name] as unknown as Screen;
  return { view: screen.view as SeaView, screen, press: vi.fn(), note: null, tg: null, ...over };
}

describe("образцы всех состояний", () => {
  for (const name of Object.keys(FIXTURES) as FixtureName[]) {
    it(`фикстура ${name} рендерится`, () => {
      const { container } = render(<Sea {...props(name)} />);
      const game = container.querySelector(".game-sea");
      expect(game).not.toBeNull();
      const view = FIXTURES[name].view;
      expect(game!.getAttribute("data-status")).toBe(view.status);
      expect(game!.getAttribute("data-turn")).toBe(view.turn ?? "");
      expect(container.firstElementChild).toMatchSnapshot(`${name}: DOM`);
    });
  }
});

describe("бой: выстрел и неактивные поля", () => {
  it("свой ход: клик по воде соперника шлёт fire с координатами", () => {
    const p = props("myTurn");
    const { container } = render(<Sea {...p} />);
    const target = container.querySelector<HTMLElement>('.game-sea [data-status] .scell[data-payload="mpf:BU54HC:3:4"]')
      ?? container.querySelector<HTMLElement>('.scell[data-payload="mpf:BU54HC:3:4"]');
    expect(target).not.toBeNull();
    fireEvent.click(target!);
    expect(p.press).toHaveBeenCalledWith("mpf:BU54HC:3:4");
  });

  it("чужой ход: у клеток соперника нет data-payload", () => {
    const { container } = render(<Sea {...props("aiThinking")} />);
    expect(container.querySelector('.scell[data-payload^="mpf:"]')).toBeNull();
  });

  it("после итога: у клеток соперника нет data-payload, корабли соперника открыты", () => {
    const { container } = render(<Sea {...props("result")} />);
    expect(container.querySelector('.scell[data-payload^="mpf:"]')).toBeNull();
    expect(container.querySelector(".k-sunk")).not.toBeNull();
    expect(container.querySelector(".result-card")!.textContent).toContain("Победа");
  });

  it("мигание: клетка blink рисует кадр сервера", () => {
    const { container } = render(<Sea {...props("blink")} />);
    // blink: board enemy, cells [[2,6]], frame hit
    expect(container.querySelector(".scell.blink-hit")).not.toBeNull();
  });
});

describe("кнопки действий — из screen.rows", () => {
  it("итог: только кнопки итога, без клеток старого поля (noop) и без второго «Меню»", () => {
    const { container } = render(<Sea {...props("result")} />);
    const texts = [...container.querySelectorAll(".sea-actions button")].map((b) => b.textContent);
    expect(texts).toEqual(["🤖 Новая партия с компьютером", "🏠 Меню"]);
    expect(container.querySelector('button[data-payload="noop"]')).toBeNull();
  });

  it("в sea-placement нет «Готов», есть «Сначала» и «Сдаться»", () => {
    const p = props("placement");
    const { container } = render(<Sea {...p} />);
    expect(container.querySelector('[data-payload="mpy:6JZGCJ"]')).toBeNull();   // нет «Готов»
    expect(container.querySelector('[data-payload="mpz:6JZGCJ"]')?.textContent).toContain("Сначала");
    expect(container.querySelector('[data-payload="mpg:6JZGCJ"]')?.textContent).toContain("Сдаться");
  });

  it("«Сдаться» с подтверждением: ок — press, отмена — ничего", () => {
    const { tg, confirms } = fakeTg();
    const p = props("myTurn", { tg });
    const { container } = render(<Sea {...p} />);
    fireEvent.click(container.querySelector<HTMLButtonElement>('[data-payload="mpg:BU54HC"]')!);
    expect(confirms).toHaveLength(1);
    expect(confirms[0]!.text).toBe("Сдаться? Это поражение.");
    expect(p.press).toHaveBeenCalledWith("mpg:BU54HC");       // фейк отвечает «ОК»

    cleanup();
    confirms.length = 0;
    const press2 = vi.fn();
    const p2 = props("myTurn", { tg, press: press2 });
    const view2 = render(<Sea {...p2} />);
    // фейк с отказом
    p2.tg!.showConfirm = (_text, callback) => { confirms.push({ text: _text, ok: false }); callback?.(false); };
    fireEvent.click(view2.container.querySelector<HTMLButtonElement>('[data-payload="mpg:BU54HC"]')!);
    expect(press2).not.toHaveBeenCalled();
  });

  it("приглашение: код крупно, «Отправить другу» открывает share-ссылку", () => {
    const { tg, links } = fakeTg();
    const p = props("invite", { tg });
    const { container } = render(<Sea {...p} />);
    expect(container.querySelector(".invite-code")?.textContent).toBe("MTXFYJ");
    fireEvent.click(container.querySelector<HTMLElement>(".invite .btn")!);
    expect(links[0]).toBe("https://t.me/share/url?url=" + encodeURIComponent("https://t.me/test_bot?start=mp_MTXFYJ"));
  });
});

describe("расстановка перетаскиванием", () => {
  /** Сетка расстановки с клеткой 30 px и gap 3: прямоугольник для перевода координат. */
  function mockGridRect() {
    const original = HTMLElement.prototype.getBoundingClientRect;
    HTMLElement.prototype.getBoundingClientRect = function (this: HTMLElement) {
      if (typeof this.className === "string" && this.className.includes("placing-board")) {
        return { left: 0, top: 0, right: 301, bottom: 352, width: 301, height: 352, x: 0, y: 0, toJSON: () => ({}) } as DOMRect;
      }
      return original.call(this);
    };
    restoreRect = () => { HTMLElement.prototype.getBoundingClientRect = original; };
  }
  let restoreRect: (() => void) | null = null;
  afterEach(() => { restoreRect?.(); restoreRect = null; });

  it("горизонтальный корабль 3: drop в клетку (0,2) → place с центром (0,2)", () => {
    mockGridRect();
    const p = props("placement");
    const { container } = render(<Sea {...p} />);
    const ship = container.querySelector<HTMLElement>(".dock-ship")!;   // первый — размер 3
    // x = 2 клетки (40+3)*2 = 86 + центр пальца, y = 20
    act(() => { fireEvent.pointerDown(ship, { clientX: 90, clientY: 20 }); });   // взял корабль: listeners подписаны
    window.dispatchEvent(new MouseEvent("pointermove", { clientX: 90, clientY: 20 }));
    act(() => { window.dispatchEvent(new MouseEvent("pointerup", { clientX: 90, clientY: 20 })); });
    // клетка drop: x=90 → c = floor(90/43)=2 → центр клетки (0,2)? cellFromPoint(90,20): c=2 (86..125), r=0
    // place с центром (0,2), o=h
    expect(p.press).toHaveBeenCalledWith("mpp:6JZGCJ:0:2:h");
  });

  it("вертикальный корабль 3 после «Повернуть»: drop (5,3) → place v с центром (5,3)", () => {
    mockGridRect();
    const p = props("placement");
    const { container } = render(<Sea {...p} />);
    fireEvent.click(container.querySelector<HTMLButtonElement>("button.rotate")!);   // вертикально
    const ship = container.querySelector<HTMLElement>(".dock-ship")!;
    // размер 4 вертикально: клетка drop (5,3) — x=114, y=175 (cell 30, gap 3)
    act(() => { fireEvent.pointerDown(ship, { clientX: 114, clientY: 175 }); });
    window.dispatchEvent(new MouseEvent("pointermove", { clientX: 114, clientY: 175 }));
    act(() => { window.dispatchEvent(new MouseEvent("pointerup", { clientX: 114, clientY: 175 })); });
    expect(p.press).toHaveBeenCalledWith("mpp:6JZGCJ:5:3:v");
  });

  it("place → кадр с current → автоматически fix (центр по правилу ядра)", async () => {
    mockGridRect();
    const p = props("placement");
    const first = render(<Sea {...p} />);
    // drop (0,1) — валидный центр корабля 3: place mpp:...:0:1:h; клетки (0,0)(0,1)(0,2)
    const ship = first.container.querySelector<HTMLElement>(".dock-ship")!;
    act(() => { fireEvent.pointerDown(ship, { clientX: 43, clientY: 10 }); });
    act(() => { window.dispatchEvent(new MouseEvent("pointerup", { clientX: 43, clientY: 10 })); });
    expect(p.press).toHaveBeenCalledWith("mpp:6JZGCJ:0:1:h");
    // сервер подтвердил: current = (0,0),(0,1),(0,2) → автоматически fix
    await act(async () => { first.rerender(<Sea {...props("placementCurrent", { press: p.press })} />); });
    expect(p.press).toHaveBeenCalledWith("mpk:6JZGCJ");
  });

  it("place отклонён (note с ошибкой) — fix не уходит", async () => {
    mockGridRect();
    const p = props("placement");
    const first = render(<Sea {...p} />);
    const ship = first.container.querySelector<HTMLElement>(".dock-ship")!;
    act(() => { fireEvent.pointerDown(ship, { clientX: 43, clientY: 10 }); });
    act(() => { window.dispatchEvent(new MouseEvent("pointerup", { clientX: 43, clientY: 10 })); });
    expect(p.press).toHaveBeenCalledWith("mpp:6JZGCJ:0:1:h");
    // сервер отклонил: current пуст, note с ошибкой → fix не шлётся
    await act(async () => { first.rerender(<Sea {...props("placement", { press: p.press, note: "Здесь корабль поставить нельзя" })} />); });
    expect(p.press).not.toHaveBeenCalledWith("mpk:6JZGCJ");
    // корабль снова в доке (док не изменился) и возвращается с анимацией
    expect(first.container.querySelectorAll(".dock-ship")).toHaveLength(6);
    expect(first.container.querySelector(".dock-ship.returning .dock-hull")?.children).toHaveLength(3);
  });

  /** Вид расстановки с одним кораблём заданного размера в доке. */
  function oneShip(size: number): GameProps<SeaView> {
    const base = props("placement");
    const view = { ...base.view, placement: { ...base.view.placement!, sizes: [size] } };
    return { ...base, view, screen: { ...base.screen, view } };
  }

  // клетка 30 px, зазор 3: центр клетки (r, c) — (c·33 + 15, r·33 + 15)
  const at = (r: number, c: number) => ({ clientX: c * 33 + 15, clientY: r * 33 + 15 });
  const shadowKeys = (root: Element) => [...root.querySelectorAll(".placing-board .scell")]
    .map((el, i) => (el.className.includes("shadow-ok") ? `${Math.floor(i / 7)}:${i % 7}` : null))
    .filter((k): k is string => k !== null);

  const CASES: Array<[number, boolean, string[]]> = [
    [1, false, ["3:3"]],
    [1, true, ["3:3"]],
    [2, false, ["3:3", "3:4"]],                  // у чётных центр — левая из двух средних
    [2, true, ["3:3", "4:3"]],                   // …и верхняя
    [3, false, ["3:2", "3:3", "3:4"]],
    [3, true, ["2:3", "3:3", "4:3"]],
    [4, false, ["3:2", "3:3", "3:4", "3:5"]],
    [4, true, ["2:3", "3:3", "4:3", "5:3"]],
  ];
  for (const [size, vertical, cells] of CASES) {
    it(`корабль ${size} ${vertical ? "вертикально" : "горизонтально"}: тень по правилу ядра, place с центром (3,3)`, () => {
      mockGridRect();
      const p = oneShip(size);
      const { container } = render(<Sea {...p} />);
      if (vertical) fireEvent.click(container.querySelector<HTMLButtonElement>("button.rotate")!);
      act(() => { fireEvent.pointerDown(container.querySelector<HTMLElement>(".dock-ship")!, at(3, 3)); });
      act(() => { window.dispatchEvent(new MouseEvent("pointermove", at(3, 3))); });
      expect(shadowKeys(container)).toEqual(cells);
      // отпускание над полем всплывает до window: place уходит ровно один раз
      const grid = container.querySelector<HTMLElement>(".placing-board")!;
      act(() => { grid.dispatchEvent(new MouseEvent("pointerup", { ...at(3, 3), bubbles: true })); });
      expect(p.press).toHaveBeenCalledTimes(1);
      expect(p.press).toHaveBeenCalledWith(`mpp:6JZGCJ:3:3:${vertical ? "v" : "h"}`);
    });
  }

  it("бросок мимо поля: place не уходит, корабль возвращается в док", () => {
    mockGridRect();
    const p = props("placement");
    const { container } = render(<Sea {...p} />);
    act(() => { fireEvent.pointerDown(container.querySelector<HTMLElement>(".dock-ship")!, at(0, 0)); });
    act(() => { window.dispatchEvent(new MouseEvent("pointerup", { clientX: 150, clientY: 500 })); });
    expect(p.press).not.toHaveBeenCalled();
    expect(container.querySelector(".dock-ship.returning")).not.toBeNull();
  });
});

describe("вибрация по разнице кадров (tz-m4 §6)", () => {
  it("свой выстрел — medium, чужой по нашему — heavy, один раз на событие", () => {
    const { tg, haptics } = fakeTg();
    const base = props("myTurn", { tg });
    const view = render(<Sea {...base} />);
    view.rerender(<Sea {...props("theirShot", { tg })} />);     // только мимо — тихо
    const withHit = JSON.parse(JSON.stringify(FIXTURES.theirShot)) as Screen;
    (withHit.view as SeaView).last = [
      { by: "me", result: "hit" },
      { by: "them", result: "miss" },
    ];
    view.rerender(<Sea {...props("theirShot", { tg, view: withHit.view as SeaView })} />);
    expect(haptics).toEqual(["impact:medium"]);
    const withThemHit = JSON.parse(JSON.stringify(withHit)) as Screen;
    (withThemHit.view as SeaView).last = [
      { by: "them", result: "hit" },
      { by: "me", result: "hit" },
    ];
    view.rerender(<Sea {...props("theirShot", { tg, view: withThemHit.view as SeaView })} />);
    expect(haptics).toEqual(["impact:medium", "impact:heavy"]);
  });

  it("итог: победа — success, поражение — error; событие один раз", () => {
    const { tg, haptics } = fakeTg();
    const base = props("myTurn", { tg });
    const view = render(<Sea {...base} />);
    // кадр итога несёт last с попаданием — по разнице кадров medium... итог: heavy+success
    view.rerender(<Sea {...props("result", { tg })} />);
    expect(haptics).toEqual(["impact:heavy", "notify:success"]);
    // тот же кадр повторно — событие не дублируется
    view.rerender(<Sea {...props("result", { tg })} />);
    expect(haptics).toEqual(["impact:heavy", "notify:success"]);
    // поражение — error
    const lost = JSON.parse(JSON.stringify(FIXTURES.result)) as Screen;
    const r = (lost.view as SeaView).result!;
    (lost.view as SeaView).result = { ...r, won: false, reason: "surrender" };
    view.rerender(<Sea {...props("result", { tg, view: lost.view as SeaView })} />);
    expect(haptics).toEqual(["impact:heavy", "notify:success", "notify:error"]);
  });
});

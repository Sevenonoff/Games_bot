// GenericScreen: ряды кнопок, клетки поля, noop, меню с плитками игр, картинка.
import { cleanup, fireEvent, render } from "@testing-library/preact";
import { afterEach, describe, expect, it, vi } from "vitest";
import { GenericScreen, isMenuScreen } from "../../src/app/GenericScreen";
import type { Screen } from "../../src/protocol";

afterEach(cleanup);

const make = (over: Partial<Screen>): Screen => ({
  text: "текст",
  rows: [],
  image: null,
  view: null,
  ...over,
});

describe("ряды кнопок", () => {
  it("ряд из одной кнопки — обычная кнопка на всю ширину", () => {
    const press = vi.fn();
    const screen = make({ rows: [[{ text: "🏠 Меню", data: "menu" }]] });
    const { container } = render(<GenericScreen screen={screen} press={press} />);
    const buttons = container.querySelectorAll("button.btn");
    expect(buttons).toHaveLength(1);
    fireEvent.click(buttons[0]!);
    expect(press).toHaveBeenCalledWith("menu");
  });

  it("ряд из 2–4 кнопок — строка кнопок", () => {
    const screen = make({
      rows: [[{ text: "a", data: "1" }, { text: "b", data: "2" }, { text: "c", data: "3" }]],
    });
    const { container } = render(<GenericScreen screen={screen} press={vi.fn()} />);
    expect(container.querySelectorAll(".row .btn")).toHaveLength(3);
  });

  it("ряд из 5–8 кнопок — сетка квадратных клеток с data-payload", () => {
    const cells = (n: number) => Array.from({ length: n }, (_, i) => ({ text: "⬜", data: `t:s:${i}` }));
    const screen = make({ rows: [cells(7)] });
    const { container } = render(<GenericScreen screen={screen} press={vi.fn()} />);
    expect(container.querySelectorAll(".cell")).toHaveLength(7);
    const grid = container.querySelector(".cells")!;
    expect(grid.getAttribute("style")).toContain("repeat(7, 1fr)");
  });

  it("кнопка noop неактивна и не шлёт press", () => {
    const press = vi.fn();
    const screen = make({ rows: [[{ text: "×", data: "noop" }]] });
    const { container } = render(<GenericScreen screen={screen} press={press} />);
    const button = container.querySelector<HTMLButtonElement>("button.btn")!;
    expect(button.disabled).toBe(true);
    fireEvent.click(button);
    expect(press).not.toHaveBeenCalled();
  });

  it("первая кнопка последнего ряда «Играть»/«Ещё раз»/«Новая партия…» — основная", () => {
    const screen = make({
      rows: [
        [{ text: "🏆 Рекорды", data: "rec" }, { text: "x", data: "y" }],
        [{ text: "🔁 Ещё раз", data: "new:memo" }, { text: "🏠 Меню", data: "menu" }],
      ],
    });
    const { container } = render(<GenericScreen screen={screen} press={vi.fn()} />);
    const primary = container.querySelector<HTMLButtonElement>("button.btn.primary");
    expect(primary?.getAttribute("data-payload")).toBe("new:memo");
  });
});

describe("меню", () => {
  const menu = make({
    text: "🎮 Игры",
    image: "/img/example.jpg",
    rows: [
      [{ text: "🎯 Тренировка дня (0/3)", data: "day" }],
      [{ text: "🃏 Мемо", data: "new:memo" }],
      [{ text: "🟦 Матрица памяти", data: "new:matrix" }],
      [{ text: "🚢 Морской бой", data: "sea" }],
      [{ text: "🏆 Рекорды", data: "rec" }],
      [{ text: "⚙️ Настройки", data: "set" }],
    ],
  });

  it("меню узнаётся по кнопке new:memo", () => {
    expect(isMenuScreen(menu)).toBe(true);
    expect(isMenuScreen(make({ rows: [[{ text: "🏠 Меню", data: "menu" }]] }))).toBe(false);
  });

  it("кнопки игр — плитками по два, с эмодзи и названием", () => {
    const { container } = render(<GenericScreen screen={menu} press={vi.fn()} />);
    const tiles = container.querySelectorAll<HTMLElement>(".tile");
    expect(tiles).toHaveLength(3);
    expect(tiles[0]!.dataset.payload).toBe("new:memo");
    expect(tiles[0]!.querySelector(".tile-emoji")?.textContent).toBe("🃏");
    expect(tiles[0]!.querySelector(".tile-name")?.textContent).toBe("Мемо");
    expect(tiles[2]!.dataset.payload).toBe("sea");
  });

  it("остальные кнопки меню — обычными рядами", () => {
    const { container } = render(<GenericScreen screen={menu} press={vi.fn()} />);
    const payloads = [...container.querySelectorAll<HTMLElement>(".row .btn")].map((b) => b.dataset.payload);
    expect(payloads).toEqual(["day", "rec", "set"]);
  });

  it("картинка меню — без отступов, со скруглением снизу", () => {
    const { container } = render(<GenericScreen screen={menu} press={vi.fn()} />);
    expect(container.querySelector(".image-box.image-menu")).not.toBeNull();
    expect(container.querySelector(".image-box img")?.getAttribute("src")).toBe("/img/example.jpg");
  });
});

describe("картинка вне меню", () => {
  it("в обычном экране — с отступами и без скругления снизу", () => {
    const screen = make({ image: "/img/card.png", rows: [] });
    const { container } = render(<GenericScreen screen={screen} press={vi.fn()} />);
    expect(container.querySelector(".image-menu")).toBeNull();
    expect(container.querySelector(".image-box")).not.toBeNull();
  });
});

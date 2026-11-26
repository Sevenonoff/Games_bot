// Геометрия корабля (tz-m4 §4, §8.6): центр по правилу ядра, клетки, границы, payload.
import { describe, expect, it } from "vitest";
import {
  canPlace, cellFromPoint, cellKey, centerIndex, centerOf, placePayload,
  shipCells, shipCellsFromStart,
} from "../../src/games/sea/geometry";

describe("центр по правилу ядра: (size − 1) // 2", () => {
  it("индексы центров для размеров 1–4", () => {
    expect(centerIndex(1)).toBe(0);
    expect(centerIndex(2)).toBe(0);   // чётные — левая/верхняя из двух средних
    expect(centerIndex(3)).toBe(1);
    expect(centerIndex(4)).toBe(1);
  });

  it("центр горизонтального и вертикального корабля", () => {
    expect(centerOf({ r: 3, c: 2 }, 3, false)).toEqual({ r: 3, c: 3 });
    expect(centerOf({ r: 3, c: 2 }, 3, true)).toEqual({ r: 4, c: 2 });
    expect(centerOf({ r: 5, c: 5 }, 2, false)).toEqual({ r: 5, c: 5 });   // размер 2: центр = начало
    expect(centerOf({ r: 5, c: 5 }, 1, true)).toEqual({ r: 5, c: 5 });
  });

  it("клетки от центра для размеров 1, 2, 3, 4 в обеих ориентациях", () => {
    expect(shipCells({ r: 1, c: 1 }, 1, false)).toEqual([{ r: 1, c: 1 }]);
    expect(shipCells({ r: 1, c: 1 }, 2, false)).toEqual([{ r: 1, c: 1 }, { r: 1, c: 2 }]);
    expect(shipCells({ r: 1, c: 1 }, 3, true)).toEqual([{ r: 0, c: 1 }, { r: 1, c: 1 }, { r: 2, c: 1 }]);
    expect(shipCells({ r: 2, c: 2 }, 4, false))
      .toEqual([{ r: 2, c: 1 }, { r: 2, c: 2 }, { r: 2, c: 3 }, { r: 2, c: 4 }]);
    expect(shipCells({ r: 2, c: 2 }, 4, true))
      .toEqual([{ r: 1, c: 2 }, { r: 2, c: 2 }, { r: 3, c: 2 }, { r: 4, c: 2 }]);
  });

  it("shipCellsFromStart согласован с центром", () => {
    const start = { r: 2, c: 2 };
    const cells = shipCellsFromStart(start, 3, false);
    expect(centerOf(start, 3, false)).toEqual({ r: 2, c: 3 });
    expect(shipCells({ r: 2, c: 3 }, 3, false)).toEqual(cells);
  });
});

describe("canPlace: только подсказка вида", () => {
  const busy = new Set(["0:0", "1:1"]);

  it("в границах и без занятых — можно", () => {
    expect(canPlace([{ r: 2, c: 2 }, { r: 2, c: 3 }], 8, 7, busy)).toBe(true);
  });

  it("за краем — нельзя", () => {
    expect(canPlace([{ r: 7, c: 6 }, { r: 7, c: 7 }], 8, 7, busy)).toBe(false);
    expect(canPlace([{ r: 0, c: 0 }], 8, 7, busy)).toBe(false);
    expect(canPlace([{ r: -1, c: 3 }], 8, 7, busy)).toBe(false);
  });

  it("на занятой — нельзя", () => {
    expect(canPlace([{ r: 1, c: 1 }], 8, 7, busy)).toBe(false);
    expect(canPlace([{ r: 0, c: 0 }, { r: 0, c: 1 }], 8, 7, busy)).toBe(false);
  });
});

describe("cellFromPoint: перевод указателя в клетку", () => {
  const cell = 40, gap = 3;

  it("центр клетки", () => {
    expect(cellFromPoint(20, 20, cell, gap, 8, 7)).toEqual({ r: 0, c: 0 });
    expect(cellFromPoint(100, 86, cell, gap, 8, 7)).toEqual({ r: 2, c: 2 });
  });

  it("в зазоре и за полем — null", () => {
    expect(cellFromPoint(41, 10, cell, gap, 8, 7)).toBeNull();   // в gap после первой клетки
    expect(cellFromPoint(-5, 10, cell, gap, 8, 7)).toBeNull();
    expect(cellFromPoint(10, 400, cell, gap, 8, 7)).toBeNull();  // ниже 8 строк
    expect(cellFromPoint(320, 10, cell, gap, 8, 7)).toBeNull();  // правее 7 колонок
  });
});

describe("placePayload: подстановка центра и ориентации", () => {
  it("шаблон actions.place", () => {
    expect(placePayload("mpp:6JZGCJ:{r}:{c}:{o}", { r: 3, c: 4 }, false))
      .toBe("mpp:6JZGCJ:3:4:h");
    expect(placePayload("mpp:6JZGCJ:{r}:{c}:{o}", { r: 0, c: 0 }, true))
      .toBe("mpp:6JZGCJ:0:0:v");
  });

  it("cellKey", () => {
    expect(cellKey({ r: 2, c: 5 })).toBe("2:5");
  });
});

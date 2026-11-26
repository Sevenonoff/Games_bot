// Геометрия корабля для расстановки перетаскиванием (tz-m4 §4) — чистые функции.
// Правила клиенту не нужны: canPlace — только подсказка вида, окончательно решает сервер.

export interface Cell {
  r: number;
  c: number;
}

/** Клетки корабля от его начала (левая/верхняя). */
export function shipCellsFromStart(start: Cell, size: number, vertical: boolean): Cell[] {
  const cells: Cell[] = [];
  for (let i = 0; i < size; i++) {
    cells.push(vertical ? { r: start.r + i, c: start.c } : { r: start.r, c: start.c + i });
  }
  return cells;
}

/** Индекс центра корабля от начала — правило ядра: (size − 1) // 2,
 *  у чётных — левая (верхняя) из двух средних. */
export function centerIndex(size: number): number {
  return (size - 1) >> 1;
}

/** Центр корабля, если его начало в start. */
export function centerOf(start: Cell, size: number, vertical: boolean): Cell {
  const i = centerIndex(size);
  return vertical ? { r: start.r + i, c: start.c } : { r: start.r, c: start.c + i };
}

/** Клетки корабля с центром в заданной клетке. */
export function shipCells(center: Cell, size: number, vertical: boolean): Cell[] {
  const i = centerIndex(size);
  const before = i;
  const after = size - 1 - i;
  const cells: Cell[] = [];
  for (let k = -before; k <= after; k++) {
    cells.push(vertical ? { r: center.r + k, c: center.c } : { r: center.r, c: center.c + k });
  }
  return cells;
}

/** Клетка под точкой указателя (координаты внутри сетки). null — вне поля. */
export function cellFromPoint(
  px: number,
  py: number,
  cell: number,
  gap: number,
  rows: number,
  cols: number,
): Cell | null {
  const stride = cell + gap;
  const c = Math.floor(px / stride);
  const r = Math.floor(py / stride);
  const inCellX = px - c * stride <= cell;
  const inCellY = py - r * stride <= cell;
  if (c < 0 || c >= cols || r < 0 || r >= rows || !inCellX || !inCellY) return null;
  return { r, c };
}

/** Подсказка вида «можно ли так поставить» — окончательно решает сервер. */
export function canPlace(
  cells: Cell[],
  rows: number,
  cols: number,
  busy: Set<string>,
): boolean {
  return cells.every(({ r, c }) =>
    r >= 0 && r < rows && c >= 0 && c < cols && !busy.has(`${r}:${c}`));
}

/** payload place: шаблон actions.place с подставленными центром и ориентацией. */
export function placePayload(template: string, center: Cell, vertical: boolean): string {
  return template
    .replace("{r}", String(center.r))
    .replace("{c}", String(center.c))
    .replace("{o}", vertical ? "v" : "h");
}

/** Ключ клетки для множеств занятых. */
export function cellKey({ r, c }: Cell): string {
  return `${r}:${c}`;
}

"""Поездка на числах (ключ игры — tower): числа на секунду появляются на поле, игрок открывает их по возрастанию.

Клетки без чисел неактивны: нажатие по ним ничего не делает.
"""
import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

IGNORED, HIT, CLEARED, MISS = "ignored", "hit", "cleared", "miss"

FIELD_COLS = 7            # больше кнопок в ряду Max не принимает
FIELD_ROWS_LIMIT = 14     # 15-й ряд — служебные кнопки
DENSITY = 0.6             # доля клеток с числами на поле 7 × N
MAX_NUMBERS = int(FIELD_COLS * FIELD_ROWS_LIMIT * DENSITY)   # 58

# уровень: (сколько чисел, мин. старт, макс. старт, макс. шаг)
TOWER_LEVELS = {
    1: (3, 1, 1, 1),
    2: (4, 1, 1, 1),
    3: (4, 2, 9, 1),
    4: (5, 2, 9, 1),
    5: (5, 1, 9, 2),
    6: (6, 1, 9, 2),
    7: (6, 1, 20, 3),
}
LATE_START_MAX = 50
LATE_STEP_MAX = 3

# (макс. чисел, сторона квадратного поля); дальше поле 7 × N
FIELD_SIDES = ((6, 3), (10, 4), (15, 5), (21, 6), (29, 7))

Cell = Tuple[int, int]


def tower_params(level: int) -> Tuple[int, int, int, int]:
    if level in TOWER_LEVELS:
        return TOWER_LEVELS[level]
    return min(level - 1, MAX_NUMBERS), 1, LATE_START_MAX, LATE_STEP_MAX


def field_size(count: int) -> Tuple[int, int]:
    """(rows, cols) поля под count чисел."""
    for max_count, side in FIELD_SIDES:
        if count <= max_count:
            return side, side
    rows = max(8, math.ceil(count / DENSITY / FIELD_COLS))
    return min(rows, FIELD_ROWS_LIMIT), FIELD_COLS


def make_numbers(level: int, rng: random.Random) -> List[int]:
    count, start_min, start_max, step_max = tower_params(level)
    value = rng.randint(start_min, start_max)
    numbers = [value]
    for _ in range(count - 1):
        value += rng.randint(1, step_max)
        numbers.append(value)
    return numbers


@dataclass
class TowerRound:
    rows: int
    cols: int
    numbers: List[int]                     # по возрастанию
    cells: Dict[Cell, int]                 # клетка -> число
    opened: int = 0                        # сколько чисел уже открыто
    _order: Dict[Cell, int] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        self._order = {cell: self.numbers.index(n) for cell, n in self.cells.items()}

    @classmethod
    def generate(cls, level: int, rng: random.Random) -> "TowerRound":
        numbers = make_numbers(level, rng)
        rows, cols = field_size(len(numbers))
        all_cells = [(r, c) for r in range(rows) for c in range(cols)]
        places = rng.sample(all_cells, len(numbers))
        return cls(rows, cols, numbers, dict(zip(places, numbers)))

    @property
    def size(self) -> int:
        return len(self.numbers)

    def is_opened(self, cell: Cell) -> bool:
        return self._order.get(cell, len(self.numbers)) < self.opened

    def tap(self, r: int, c: int) -> str:
        cell = (r, c)
        if cell not in self.cells or self.is_opened(cell):
            return IGNORED
        if self._order[cell] != self.opened:
            return MISS
        self.opened += 1
        return CLEARED if self.opened == len(self.numbers) else HIT

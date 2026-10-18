"""Матрица памяти: на секунду показываются клетки, игрок их восстанавливает."""
import math
import random
from dataclasses import dataclass, field
from typing import Set, Tuple

IGNORED, HIT, CLEARED, MISS = "ignored", "hit", "cleared", "miss"

MAX_CELLS = 60
FIELD_ROWS_LIMIT = 14     # 15-й ряд — служебные кнопки
TARGET_DENSITY = 0.42

# (последний уровень, сторона квадратного поля)
SQUARE_FIELDS = ((2, 3), (5, 4), (9, 5), (14, 6), (20, 7), (27, 8), (35, 9))

Cell = Tuple[int, int]


def matrix_params(level: int) -> Tuple[int, int, int]:
    """(rows, cols, n) для уровня."""
    n = min(level + 2, MAX_CELLS)
    for last_level, side in SQUARE_FIELDS:
        if level <= last_level:
            return side, side, n
    cols = 10
    rows = max(10, math.ceil(n / TARGET_DENSITY / cols))
    return min(rows, FIELD_ROWS_LIMIT), cols, n


@dataclass
class MatrixRound:
    rows: int
    cols: int
    targets: Set[Cell]
    found: Set[Cell] = field(default_factory=set)

    @classmethod
    def generate(cls, level: int, rng: random.Random) -> "MatrixRound":
        rows, cols, n = matrix_params(level)
        cells = [(r, c) for r in range(rows) for c in range(cols)]
        return cls(rows, cols, set(rng.sample(cells, n)))

    @property
    def size(self) -> int:
        return len(self.targets)

    def tap(self, r: int, c: int) -> str:
        cell = (r, c)
        if not (0 <= r < self.rows and 0 <= c < self.cols) or cell in self.found:
            return IGNORED
        if cell not in self.targets:
            return MISS
        self.found.add(cell)
        return CLEARED if self.found == self.targets else HIT

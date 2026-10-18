"""Башня чисел: числа на секунду появляются на поле, игрок открывает их по возрастанию."""
import random
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

IGNORED, HIT, CLEARED, MISS = "ignored", "hit", "cleared", "miss"

MAX_NUMBERS = 60

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

# (макс. чисел, сторона поля)
FIELD_SIDES = ((6, 3), (10, 4), (15, 5), (21, 6), (29, 7), (38, 8), (48, 9), (MAX_NUMBERS, 10))

Cell = Tuple[int, int]


def tower_params(level: int) -> Tuple[int, int, int, int]:
    if level in TOWER_LEVELS:
        return TOWER_LEVELS[level]
    return min(level - 1, MAX_NUMBERS), 1, LATE_START_MAX, LATE_STEP_MAX


def field_side(count: int) -> int:
    for max_count, side in FIELD_SIDES:
        if count <= max_count:
            return side
    return FIELD_SIDES[-1][1]


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
    side: int
    numbers: List[int]                     # по возрастанию
    cells: Dict[Cell, int]                 # клетка -> число
    opened: int = 0                        # сколько чисел уже открыто
    _by_number: Dict[int, Cell] = field(default_factory=dict, repr=False)

    def __post_init__(self):
        self._by_number = {n: cell for cell, n in self.cells.items()}

    @classmethod
    def generate(cls, level: int, rng: random.Random) -> "TowerRound":
        numbers = make_numbers(level, rng)
        side = field_side(len(numbers))
        all_cells = [(r, c) for r in range(side) for c in range(side)]
        places = rng.sample(all_cells, len(numbers))
        return cls(side, numbers, dict(zip(places, numbers)))

    @property
    def rows(self) -> int:
        return self.side

    @property
    def cols(self) -> int:
        return self.side

    @property
    def size(self) -> int:
        return len(self.numbers)

    def is_opened(self, cell: Cell) -> bool:
        n = self.cells.get(cell)
        return n is not None and self.numbers.index(n) < self.opened

    def tap(self, r: int, c: int) -> str:
        cell = (r, c)
        if not (0 <= r < self.side and 0 <= c < self.side) or self.is_opened(cell):
            return IGNORED
        if self._by_number[self.numbers[self.opened]] != cell:
            return MISS
        self.opened += 1
        return CLEARED if self.opened == len(self.numbers) else HIT

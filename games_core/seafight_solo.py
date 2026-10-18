"""Морской бой, одиночная игра: найти и потопить все корабли.

Генерация поля перенесена из sea_fight_aiogram/utils/game_logic.py; клетки
хранятся как состояния, а не как эмодзи. Индексация board[r][c].
"""
import random
from dataclasses import dataclass, field
from typing import List, Optional, Set, Tuple

ROWS = 8
COLS = 8
SHIP_SETS = {
    "full": [4, 3, 3, 2, 2, 2, 1, 1, 1, 1],
    "reduced": [3, 2, 2, 1, 1, 1],
}
HIT_POINTS = 10
MISS_POINTS = -1

IGNORED, MISS, HIT, SUNK, WON = "ignored", "miss", "hit", "sunk", "won"

# состояние клетки на поле выстрелов
UNKNOWN, SHOT_MISS, SHOT_HIT, SHOT_SUNK = ".", "o", "x", "#"

Cell = Tuple[int, int]


def generate_ships(sizes: List[int], rng: random.Random, rows: int = ROWS, cols: int = COLS,
                   attempts: int = 20, tries: int = 100) -> List[List[Cell]]:
    """Случайная расстановка: корабли не касаются друг друга даже углами."""
    for _ in range(attempts):
        occupied: Set[Cell] = set()
        blocked: Set[Cell] = set()
        ships: List[List[Cell]] = []
        for size in sizes:
            for _ in range(tries):
                r, c = rng.randrange(rows), rng.randrange(cols)
                if rng.random() < 0.5:
                    cells = [(r, c + i) for i in range(size)]
                else:
                    cells = [(r + i, c) for i in range(size)]
                if all(0 <= y < rows and 0 <= x < cols and (y, x) not in blocked for y, x in cells):
                    ships.append(cells)
                    occupied.update(cells)
                    blocked.update((y + dy, x + dx) for y, x in cells
                                   for dy in (-1, 0, 1) for dx in (-1, 0, 1))
                    break
            else:
                break
        if len(ships) == len(sizes):
            return ships
    raise RuntimeError("не удалось расставить корабли")


@dataclass
class SeaBoard:
    ships: List[List[Cell]]
    rows: int = ROWS
    cols: int = COLS
    shots: List[List[str]] = field(default_factory=list)
    score: int = 0

    def __post_init__(self):
        if not self.shots:
            self.shots = [[UNKNOWN] * self.cols for _ in range(self.rows)]

    @classmethod
    def generate(cls, ship_set: str, rng: random.Random) -> "SeaBoard":
        return cls(generate_ships(SHIP_SETS[ship_set], rng))

    def ship_at(self, cell: Cell) -> Optional[List[Cell]]:
        for ship in self.ships:
            if cell in ship:
                return ship
        return None

    def is_won(self) -> bool:
        return all(self.shots[r][c] != UNKNOWN for ship in self.ships for r, c in ship)

    def fire(self, r: int, c: int) -> str:
        if not (0 <= r < self.rows and 0 <= c < self.cols) or self.shots[r][c] != UNKNOWN:
            return IGNORED
        ship = self.ship_at((r, c))
        if ship is None:
            self.shots[r][c] = SHOT_MISS
            self.score += MISS_POINTS
            return MISS
        self.shots[r][c] = SHOT_HIT
        self.score += HIT_POINTS
        if all(self.shots[y][x] == SHOT_HIT for y, x in ship):
            for y, x in ship:
                self.shots[y][x] = SHOT_SUNK
            return WON if self.is_won() else SUNK
        return HIT

"""Проложи дорогу: на поле человек, дом и препятствия.

Игрок кладёт дорогу по клеткам в любом порядке, не наступая на препятствия; раунд пройден,
как только клетки дороги соединили человека с домом по соседним (по сторонам) клеткам.
Нажатие на препятствие — ошибка; на человека, дом или уже положенную клетку — ничего.
Длина дороги — число её клеток.
"""
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

IGNORED, HIT, CLEARED, MISS = "ignored", "hit", "cleared", "miss"

FIELD_COLS = 7            # больше кнопок в ряду Max не принимает
FIELD_ROWS_LIMIT = 14     # 15-й ряд — служебные кнопки
MIN_ENDS_DISTANCE = 3     # никакая клетка не соседствует и с человеком, и с домом
GENERATE_TRIES = 500

# без эмодзи с вариационным селектором: они могут рисоваться как текст
PEOPLE = ("🧑", "👩", "👨", "👧", "👦", "👵", "👴")
HOUSES = ("🏠", "🏡", "🏫", "🏥", "🏰", "🏪", "⛺")

# уровень: (рядов, колонок, доля красных, мин. длина кратчайшего пути)
PATH_LEVELS = {
    1: (4, 4, 0.20, 2),
    2: (4, 4, 0.25, 2),
    3: (5, 5, 0.25, 3),
    4: (5, 5, 0.30, 3),
    5: (6, 6, 0.30, 4),
    6: (6, 6, 0.33, 4),
    7: (7, 7, 0.33, 5),
}
LATE_DENSITY_MAX = 0.40

Cell = Tuple[int, int]


def path_params(level: int) -> Tuple[int, int, float, int]:
    if level in PATH_LEVELS:
        return PATH_LEVELS[level]
    extra = level - max(PATH_LEVELS)
    rows = min(FIELD_COLS + (extra + 1) // 2, FIELD_ROWS_LIMIT)
    return rows, FIELD_COLS, min(0.33 + 0.01 * extra, LATE_DENSITY_MAX), min(5 + extra // 2, 9)


def distance(a: Cell, b: Cell) -> int:
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


@dataclass
class PathRound:
    rows: int
    cols: int
    ends: Tuple[Cell, Cell]                # человек и дом
    blocks: Set[Cell]
    icons: Tuple[str, str] = (PEOPLE[0], HOUSES[0])
    road: List[Cell] = field(default_factory=list)       # клетки дороги в порядке нажатий
    solution: List[Cell] = field(default_factory=list)   # одна из кратчайших дорог (для разбора)

    def __post_init__(self):
        if not self.solution:
            self.solution = self.shortest_route() or []

    @classmethod
    def generate(cls, level: int, rng: random.Random) -> "PathRound":
        rows, cols, density, min_len = path_params(level)
        cells = [(r, c) for r in range(rows) for c in range(cols)]
        icons = (rng.choice(PEOPLE), rng.choice(HOUSES))
        best = None
        for _ in range(GENERATE_TRIES):
            a, b = rng.sample(cells, 2)
            if distance(a, b) < MIN_ENDS_DISTANCE:
                continue
            others = [x for x in cells if x not in (a, b)]
            blocks = set(rng.sample(others, max(1, round(len(cells) * density))))
            rnd = cls(rows, cols, (a, b), blocks, icons)
            if rnd.solution and len(rnd.solution) >= min_len:
                return rnd
            if rnd.solution and (best is None or len(rnd.solution) > len(best.solution)):
                best = rnd
        if best is not None:
            return best
        # почти невероятно: поле без препятствий, кроме одного в углу подальше от концов
        a, b = (0, 0), (rows - 1, cols - 1)
        return cls(rows, cols, (a, b), {(0, cols - 1)}, icons)

    # --- геометрия ---

    def inside(self, cell: Cell) -> bool:
        return 0 <= cell[0] < self.rows and 0 <= cell[1] < self.cols

    def neighbors(self, cell: Cell) -> List[Cell]:
        r, c = cell
        return [x for x in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)) if self.inside(x)]

    def free(self, cell: Cell) -> bool:
        """Сюда можно положить дорогу."""
        return self.inside(cell) and cell not in self.blocks and cell not in self.ends

    def route(self, sources: Iterable[Cell], goal: Set[Cell], blocked: Set[Cell] = frozenset()) -> Optional[List[Cell]]:
        """Кратчайший путь (BFS) от любой из sources до любой клетки goal по свободным клеткам,
        кроме blocked."""
        sources = [s for s in sources if self.free(s) and s not in blocked]
        prev: Dict[Cell, Optional[Cell]] = {s: None for s in sources}
        queue = deque(sources)
        while queue:
            cell = queue.popleft()
            if cell in goal:
                out = []
                while cell is not None:
                    out.append(cell)
                    cell = prev[cell]
                return out[::-1]
            for x in self.neighbors(cell):
                if x not in prev and self.free(x) and x not in blocked:
                    prev[x] = cell
                    queue.append(x)
        return None

    def shortest_route(self) -> Optional[List[Cell]]:
        a, b = self.ends
        return self.route(self.neighbors(a), set(self.neighbors(b)))

    @property
    def shortest(self) -> int:
        return len(self.solution)

    @property
    def size(self) -> int:
        return self.shortest

    def length(self) -> int:
        return len(self.road)

    def is_shortest(self) -> bool:
        return self.length() == self.shortest

    def connected(self) -> bool:
        """Дорога соединяет человека с домом."""
        a, b = self.ends
        road = set(self.road)
        seen, queue = {a}, deque([a])
        while queue:
            for x in self.neighbors(queue.popleft()):
                if x == b:
                    return True
                if x in road and x not in seen:
                    seen.add(x)
                    queue.append(x)
        return False

    # --- ход ---

    def tap(self, r: int, c: int) -> str:
        cell = (r, c)
        if not self.inside(cell) or cell in self.ends or cell in self.road:
            return IGNORED
        if cell in self.blocks:
            return MISS
        self.road.append(cell)
        return CLEARED if self.connected() else HIT

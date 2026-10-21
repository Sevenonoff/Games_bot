"""Соедини зелёные: на открытом поле два зелёных квадрата и красные клетки.

Игрок прокладывает путь по соседним (по сторонам) клеткам от одного зелёного к другому,
не наступая на красные. Начать можно с зелёного или рядом с ним; путь готов, как только
дошёл до второго зелёного или встал рядом с ним. Любое неверное нажатие — ошибка.
Длина пути — число его не зелёных клеток: так начало «с зелёного» и «рядом» равноценны.
"""
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

IGNORED, HIT, CLEARED, MISS = "ignored", "hit", "cleared", "miss"
RED, FAR_START, NOT_ADJACENT, REVISIT = "red", "far_start", "not_adjacent", "revisit"   # причины ошибки

FIELD_COLS = 7            # больше кнопок в ряду Max не принимает
FIELD_ROWS_LIMIT = 14     # 15-й ряд — служебные кнопки
MIN_GREEN_DISTANCE = 3    # никакая клетка не соседствует с обоими зелёными
GENERATE_TRIES = 500

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
    greens: Tuple[Cell, Cell]
    reds: Set[Cell]
    path: List[Cell] = field(default_factory=list)
    start_green: Optional[Cell] = None     # от какого зелёного начат путь
    miss_reason: Optional[str] = None
    solution: List[Cell] = field(default_factory=list)   # один из кратчайших путей (для разбора)

    def __post_init__(self):
        if not self.solution:
            self.solution = self.shortest_route() or []

    @classmethod
    def generate(cls, level: int, rng: random.Random) -> "PathRound":
        rows, cols, density, min_len = path_params(level)
        cells = [(r, c) for r in range(rows) for c in range(cols)]
        best = None
        for _ in range(GENERATE_TRIES):
            a, b = rng.sample(cells, 2)
            if distance(a, b) < MIN_GREEN_DISTANCE:
                continue
            others = [x for x in cells if x not in (a, b)]
            reds = set(rng.sample(others, max(1, round(len(cells) * density))))
            rnd = cls(rows, cols, (a, b), reds)
            if rnd.solution and len(rnd.solution) >= min_len:
                return rnd
            if rnd.solution and (best is None or len(rnd.solution) > len(best.solution)):
                best = rnd
        if best is not None:
            return best
        # почти невероятно: поле без красных, кроме одной в углу подальше от зелёных
        a, b = (0, 0), (rows - 1, cols - 1)
        return cls(rows, cols, (a, b), {(0, cols - 1)})

    # --- геометрия ---

    def inside(self, cell: Cell) -> bool:
        return 0 <= cell[0] < self.rows and 0 <= cell[1] < self.cols

    def neighbors(self, cell: Cell) -> List[Cell]:
        r, c = cell
        return [x for x in ((r - 1, c), (r + 1, c), (r, c - 1), (r, c + 1)) if self.inside(x)]

    def near(self, green: Cell) -> Set[Cell]:
        """Зелёный и его не красные соседи: тут путь может начаться или закончиться."""
        return {green} | {x for x in self.neighbors(green) if x not in self.reds}

    def other_green(self, green: Cell) -> Cell:
        return self.greens[1] if green == self.greens[0] else self.greens[0]

    def route(self, sources: Iterable[Cell], goal: Set[Cell], blocked: Set[Cell] = frozenset()) -> Optional[List[Cell]]:
        """Кратчайший путь (BFS) от любой из sources до любой клетки goal по свободным клеткам:
        не красным, не blocked и не зелёным — начинать путь с самого зелёного незачем,
        а у второго зелёного путь и так готов.
        """
        sources = [s for s in sources if s not in self.reds and s not in blocked and s not in self.greens]
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
                if x not in prev and x not in self.reds and x not in blocked and x not in self.greens:
                    prev[x] = cell
                    queue.append(x)
        return None

    def shortest_route(self) -> Optional[List[Cell]]:
        a, b = self.greens
        return self.route(self.near(a) - {a}, self.near(b))

    @property
    def shortest(self) -> int:
        return len(self.solution)

    @property
    def size(self) -> int:
        return self.shortest

    def length(self) -> int:
        return sum(1 for x in self.path if x not in self.greens)

    def is_shortest(self) -> bool:
        return self.length() == self.shortest

    # --- ход ---

    def tap(self, r: int, c: int) -> str:
        cell = (r, c)
        if not self.inside(cell):
            return IGNORED
        reason = self._check(cell)
        if reason is not None:
            self.miss_reason = reason
            return MISS
        if not self.path:
            self.start_green = next(g for g in self.greens if cell in self.near(g))
        self.path.append(cell)
        if cell in self.near(self.other_green(self.start_green)):
            return CLEARED
        return HIT

    def _check(self, cell: Cell) -> Optional[str]:
        if cell in self.reds:
            return RED
        if not self.path:
            return None if any(cell in self.near(g) for g in self.greens) else FAR_START
        if cell in self.path:
            return REVISIT
        if cell not in self.neighbors(self.path[-1]):
            return NOT_ADJACENT
        return None

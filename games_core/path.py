"""Проложи дорогу: на поле человек, дом и препятствия.

Игрок кладёт дорогу по клеткам в любом порядке, не наступая на препятствия; раунд пройден,
как только клетки дороги соединили человека с домом по соседним (по сторонам) клеткам.
Нажатие на препятствие — ошибка; на уже положенную клетку — ничего. Нажатие на человека или
дом выглядит как обычная клетка дороги (иначе по «ничего не случилось» их можно найти),
но в дорогу не входит. Длина дороги — число её клеток.
"""
import random
from collections import deque
from dataclasses import dataclass, field
from typing import Dict, Iterable, List, Optional, Set, Tuple

IGNORED, HIT, CLEARED, MISS = "ignored", "hit", "cleared", "miss"

FIELD_COLS = 7            # больше кнопок в ряду Max не принимает
FIELD_ROWS_LIMIT = 14     # 15-й ряд — служебные кнопки
MIN_ENDS_DISTANCE = 3     # никакая клетка не соседствует и с человеком, и с домом
GENERATE_TRIES = 3000

# без эмодзи с вариационным селектором: они могут рисоваться как текст
# человек во весь рост: силуэт заметнее лица
PEOPLE = ("🚶", "🏃", "🧍", "💃", "🕺")
HOUSES = ("🏠", "🏡", "🏫", "🏥", "🏰", "🏪")


@dataclass(frozen=True)
class PathLevel:
    """Поле и сложность дороги уровня. Дорога — кратчайшая с наименьшим числом поворотов:
    её повороты и длина должны попасть в диапазоны уровня."""
    rows: int
    cols: int
    blocks: int               # сколько препятствий
    turns: Tuple[int, int]    # повороты, от и до (вход от человека и выход к дому тоже считаются)
    length: Tuple[int, int]   # клеток дороги, от и до


# Поле и препятствия растут медленно, а на каждом поле дорога становится сложнее:
# больше поворотов и длиннее. Диапазоны подобраны замером: каждая комбинация встречается
# не реже чем на ~2% случайных полей, генератор находит её за доли секунды.
PATH_LEVELS = {
    1: PathLevel(4, 4, 3, (0, 1), (2, 3)),
    2: PathLevel(4, 4, 3, (1, 1), (3, 4)),
    3: PathLevel(4, 4, 4, (2, 2), (3, 5)),
    4: PathLevel(5, 5, 5, (1, 1), (3, 5)),
    5: PathLevel(5, 5, 5, (2, 2), (4, 6)),
    6: PathLevel(5, 5, 6, (3, 3), (4, 7)),
    7: PathLevel(6, 6, 8, (1, 2), (4, 6)),
    8: PathLevel(6, 6, 8, (2, 3), (5, 7)),
    9: PathLevel(6, 6, 10, (3, 3), (5, 8)),
    10: PathLevel(6, 6, 10, (4, 4), (6, 9)),
    11: PathLevel(7, 7, 12, (2, 2), (5, 8)),
    12: PathLevel(7, 7, 13, (3, 3), (6, 9)),
    13: PathLevel(7, 7, 14, (4, 4), (7, 10)),
    14: PathLevel(7, 7, 15, (5, 5), (8, 12)),
}
LATE_STEPS = 4            # дальше: блоки по 4 уровня, в блоке поле на ряд больше
LATE_DENSITY = 0.31       # доля препятствий на поздних уровнях

Cell = Tuple[int, int]
DIRECTIONS = ((-1, 0), (1, 0), (0, -1), (0, 1))


def path_params(level: int) -> PathLevel:
    if level in PATH_LEVELS:
        return PATH_LEVELS[level]
    extra = max(0, level - max(PATH_LEVELS) - 1)
    block, step = divmod(extra, LATE_STEPS)
    last_block = FIELD_ROWS_LIMIT - FIELD_COLS - 1
    if block > last_block:
        # поле больше не растёт — остаётся самая сложная дорога самого большого поля
        block, step = last_block, LATE_STEPS - 1
    rows = FIELD_COLS + 1 + block
    turns = 2 + step
    shortest = turns + 3 + block // 2
    return PathLevel(rows, FIELD_COLS, round(rows * FIELD_COLS * LATE_DENSITY), (turns, turns),
                     (shortest, shortest + (4 if turns >= 5 else 3)))


def band_miss(value: int, band: Tuple[int, int]) -> int:
    """На сколько value выходит за диапазон band (0 — внутри)."""
    return max(band[0] - value, value - band[1], 0)


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
    marked: Set[Cell] = field(default_factory=set)       # нажатые человек и дом: вслепую — как дорога
    solution: List[Cell] = field(default_factory=list)   # самая простая из кратчайших дорог (для разбора)
    _turns: Optional[int] = field(default=None, init=False, repr=False)

    def __post_init__(self):
        if not self.solution:
            self.solution = self.simplest_route() or []

    @classmethod
    def generate(cls, level: int, rng: random.Random) -> "PathRound":
        spec = path_params(level)
        rows, cols = spec.rows, spec.cols
        cells = [(r, c) for r in range(rows) for c in range(cols)]
        icons = (rng.choice(PEOPLE), rng.choice(HOUSES))
        best, best_miss = None, None
        for _ in range(GENERATE_TRIES):
            a, b = rng.sample(cells, 2)
            if distance(a, b) < MIN_ENDS_DISTANCE:
                continue
            others = [x for x in cells if x not in (a, b)]
            blocks = set(rng.sample(others, min(spec.blocks, len(others) - 1)))
            rnd = cls(rows, cols, (a, b), blocks, icons)
            if not rnd.solution:
                continue
            miss = band_miss(rnd.turns, spec.turns) + band_miss(rnd.shortest, spec.length)
            if miss == 0:
                return rnd
            if best_miss is None or miss < best_miss:
                best, best_miss = rnd, miss
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

    def _distances(self, start: Cell) -> Dict[Cell, int]:
        """Шаги от start по свободным клеткам; концы достижимы, но сквозь них не пройти."""
        dist = {start: 0}
        queue = deque([start])
        while queue:
            cell = queue.popleft()
            for x in self.neighbors(cell):
                if x not in dist and (self.free(x) or x in self.ends):
                    dist[x] = dist[cell] + 1
                    if x not in self.ends:
                        queue.append(x)
        return dist

    def simplest_route(self) -> Optional[List[Cell]]:
        """Кратчайшая дорога с наименьшим числом поворотов (её и проще всего запомнить).
        Клетки — по порядку от человека к дому, без самих концов."""
        a, b = self.ends
        from_a, from_b = self._distances(a), self._distances(b)
        if b not in from_a:
            return None
        total = from_a[b]

        def on_route(cell: Cell, step: int) -> bool:
            return from_a.get(cell) == step and from_b.get(cell) == total - step

        # лучшее число поворотов до (клетка, направление входа) и откуда пришли
        best: Dict[Tuple[Cell, int], Tuple[int, Optional[Tuple[Cell, int]]]] = {}
        layer: List[Tuple[Cell, int]] = []
        for d, (dr, dc) in enumerate(DIRECTIONS):
            x = (a[0] + dr, a[1] + dc)
            if x != b and on_route(x, 1):
                best[(x, d)] = (0, None)
                layer.append((x, d))
        for step in range(1, total):
            following = []
            for state in layer:
                (r, c), d = state
                turns = best[state][0]
                for nd, (dr, dc) in enumerate(DIRECTIONS):
                    x = (r + dr, c + dc)
                    if not on_route(x, step + 1):
                        continue
                    value = turns + (nd != d)
                    if (x, nd) not in best:
                        following.append((x, nd))
                    if (x, nd) not in best or value < best[(x, nd)][0]:
                        best[(x, nd)] = (value, state)
            layer = following
        end = min((s for s in best if s[0] == b), key=lambda s: best[s][0])
        self._turns = best[end][0]
        out, state = [], best[end][1]
        while state is not None:
            out.append(state[0])
            state = best[state][1]
        return out[::-1]

    @property
    def turns(self) -> int:
        """Повороты самой простой кратчайшей дороги."""
        if self._turns is None:
            self.simplest_route()
        return self._turns or 0

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
        if not self.inside(cell) or cell in self.road or cell in self.marked:
            return IGNORED
        if cell in self.blocks:
            return MISS
        if cell in self.ends:
            self.marked.add(cell)
            return HIT
        self.road.append(cell)
        return CLEARED if self.connected() else HIT

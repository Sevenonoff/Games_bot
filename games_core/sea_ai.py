"""Компьютер в морском бое. Не подглядывает: видит только свои выстрелы.

Вход — choose_shot(shots, sizes, level, rng): сетка выстрелов компьютера по полю
соперника (UNKNOWN / SHOT_MISS / SHOT_HIT / SHOT_SUNK, ровно Side.shots) и набор
кораблей. Партию и корабли соперника функция не получает.

«Продвинутый» (ADVANCED) стреляет туда, где корабль вероятнее всего: вероятность
клетки — доля всех расстановок оставшихся кораблей, согласных с увиденным
(корабли не касаются даже углами), в которых клетка занята. Когда расстановок
немного — считаем их все точно; когда много (начало партии) — оцениваем
последовательным сэмплированием с весами. Добивание раненого и обход клеток
вокруг потопленных получаются сами собой.

Доказуемо оптимальную стратегию (минимум ожидаемых выстрелов) за разумное время
не посчитать; «стреляй туда, где вероятность выше» — сильнейшая известная
практическая стратегия. Замер (2026-11-21, до победы, среднее): полный набор —
26.5 выстрела против 31.9 у «шахматной охоты с добиванием» и 34.5 у «обычного»;
малый набор — 32.4 / 31.9 / 36.1: там всё решает поиск трёх однопалубных,
и сильная стратегия почти не помогает.

«Обычный» (NORMAL) играет как человек: ищет наугад, после попадания пробует
соседние клетки, но часто ошибается — стреляет рядом с потопленным кораблём,
бросает добивание ради случайной клетки, идёт не вдоль линии.
"""
import random
import time
from collections import Counter
from math import factorial
from typing import Dict, List, Optional, Sequence, Tuple

from .seafight_solo import SHOT_HIT, SHOT_MISS, SHOT_SUNK, UNKNOWN

Cell = Tuple[int, int]

NORMAL, ADVANCED = "normal", "advanced"
LEVELS = (NORMAL, ADVANCED)

# «обычный»: доля ошибочных ходов
NORMAL_MISTAKE = 0.3

# «продвинутый»: точный перебор, если расстановок не больше EXACT_NODES узлов поиска,
# иначе сэмплирование: не дольше SAMPLE_SECONDS и не больше SAMPLE_MAX расстановок
EXACT_NODES = 20_000
SAMPLE_SECONDS = 0.25
SAMPLE_MIN = 300
SAMPLE_MAX = 4_000


def choose_shot(shots: Sequence[Sequence[str]], sizes: Sequence[int], level: str,
                rng: random.Random) -> Cell:
    """Клетка следующего выстрела: всегда необстрелянная."""
    view = View(shots, sizes)
    if not view.unknown:
        raise ValueError("на поле не осталось необстрелянных клеток")
    if level == ADVANCED:
        return view.best(rng)
    return view.human(rng)


# --- разбор увиденного ---

class View:
    def __init__(self, shots: Sequence[Sequence[str]], sizes: Sequence[int]):
        self.rows, self.cols = len(shots), len(shots[0])
        self.shots = shots
        self.unknown = [(r, c) for r in range(self.rows) for c in range(self.cols) if shots[r][c] == UNKNOWN]
        self.hits = [(r, c) for r in range(self.rows) for c in range(self.cols) if shots[r][c] == SHOT_HIT]
        sunk = self._groups(SHOT_SUNK)
        self.remaining = Counter(sizes)
        for ship in sunk:
            self.remaining[len(ship)] -= 1
        self.consistent = all(n >= 0 for n in self.remaining.values())
        self.remaining = Counter({s: n for s, n in self.remaining.items() if n > 0})
        # клетки, где корабля точно нет: промахи, потопленные и всё вокруг них, углы раненых
        empty = {(r, c) for r in range(self.rows) for c in range(self.cols) if shots[r][c] == SHOT_MISS}
        for ship in sunk:
            empty |= self.around(ship)
        for r, c in self.hits:
            empty |= {(r + dr, c + dc) for dr in (-1, 1) for dc in (-1, 1) if self.inside(r + dr, c + dc)}
        self.empty = empty - set(self.hits)

    def inside(self, r: int, c: int) -> bool:
        return 0 <= r < self.rows and 0 <= c < self.cols

    def around(self, cells) -> set:
        return {(r + dr, c + dc) for r, c in cells for dr in (-1, 0, 1) for dc in (-1, 0, 1)
                if self.inside(r + dr, c + dc)}

    def _groups(self, state: str) -> List[List[Cell]]:
        """Связные (по сторонам) группы клеток в этом состоянии: корабли не касаются, группы однозначны."""
        seen, groups = set(), []
        for r in range(self.rows):
            for c in range(self.cols):
                if self.shots[r][c] != state or (r, c) in seen:
                    continue
                group, stack = [], [(r, c)]
                seen.add((r, c))
                while stack:
                    y, x = stack.pop()
                    group.append((y, x))
                    for ny, nx in ((y + 1, x), (y - 1, x), (y, x + 1), (y, x - 1)):
                        if self.inside(ny, nx) and (ny, nx) not in seen and self.shots[ny][nx] == state:
                            seen.add((ny, nx))
                            stack.append((ny, nx))
                groups.append(group)
        return groups

    # --- «продвинутый» ---

    def best(self, rng: random.Random) -> Cell:
        weights = self.probabilities(rng)
        candidates = [cell for cell in self.unknown if cell not in self.empty] or self.unknown
        top = max(weights.get(cell, 0.0) for cell in candidates)
        if top <= 0:
            return rng.choice(candidates)
        best = [cell for cell in candidates if weights.get(cell, 0.0) >= top * (1 - 1e-9)]
        return rng.choice(best)

    def probabilities(self, rng: random.Random) -> Dict[Cell, float]:
        """Клетка → вес «здесь корабль» (пропорционален вероятности)."""
        if not self.consistent or not self.remaining:
            return {}
        space = Space(self)
        weights = space.exact(EXACT_NODES)
        if weights is None:
            weights = space.sampled(rng)
        return weights

    # --- «обычный» ---

    def human(self, rng: random.Random) -> Cell:
        careful = [cell for cell in self.unknown if cell not in self.empty] or self.unknown
        mistake = rng.random() < NORMAL_MISTAKE
        if self.hits:
            targets = self._next_to_hits(careful, sloppy=mistake and rng.random() < 0.5)
            if targets and not (mistake and rng.random() < 0.5):
                return rng.choice(targets)
            return rng.choice(self.unknown)
        if mistake:
            return rng.choice(self.unknown)          # в том числе рядом с потопленным
        return rng.choice(careful)

    def _next_to_hits(self, careful: List[Cell], sloppy: bool) -> List[Cell]:
        """Куда добивать: по линии раненых, если их два и больше (sloppy — любые соседи)."""
        allowed = set(careful)
        hits = set(self.hits)

        def free(r, c):
            return (r, c) in allowed

        line = []
        if not sloppy:
            for r, c in hits:
                for dr, dc in ((0, 1), (1, 0)):
                    if (r + dr, c + dc) in hits:
                        # продолжить линию в обе стороны
                        for sign in (1, -1):
                            y, x = r, c
                            while (y, x) in hits:
                                y, x = y + sign * dr, x + sign * dc
                            if free(y, x):
                                line.append((y, x))
        if line:
            return line
        return [(r + dr, c + dc) for r, c in hits for dr, dc in ((0, 1), (1, 0), (0, -1), (-1, 0))
                if free(r + dr, c + dc)]


# --- пространство расстановок оставшихся кораблей ---

class Space:
    """Корабли и клетки — битовые маски; placements[size] = [(клетки, клетки с ореолом)]."""

    def __init__(self, view: View):
        rows, cols = view.rows, view.cols
        self.view = view
        self.cell_bit = {(r, c): 1 << (r * cols + c) for r in range(rows) for c in range(cols)}
        self.bit_cell = {b: cell for cell, b in self.cell_bit.items()}
        empty = 0
        for cell in view.empty:
            empty |= self.cell_bit[cell]
        self.hits = 0
        for cell in view.hits:
            self.hits |= self.cell_bit[cell]
        self.sizes = sorted(view.remaining.elements(), reverse=True)
        self.placements: Dict[int, List[Tuple[int, int]]] = {}
        for size in set(self.sizes):
            out = []
            for r in range(rows):
                for c in range(cols):
                    for vertical in ((False, True) if size > 1 else (False,)):
                        cells = [(r + i, c) if vertical else (r, c + i) for i in range(size)]
                        if not all(view.inside(y, x) for y, x in cells):
                            continue
                        mask = 0
                        for cell in cells:
                            mask |= self.cell_bit[cell]
                        if mask & empty:
                            continue
                        if not mask & ~self.hits:
                            # корабль из одних раненых клеток уже был бы потоплен: раненый — длиннее
                            continue
                        halo = 0
                        for cell in view.around(cells):
                            halo |= self.cell_bit[cell]
                        out.append((mask, halo))
            self.placements[size] = out

    def _to_cells(self, masks: Dict[int, float]) -> Dict[Cell, float]:
        weights: Dict[Cell, float] = {}
        for mask, w in masks.items():
            while mask:
                low = mask & -mask
                cell = self.bit_cell[low]
                weights[cell] = weights.get(cell, 0.0) + w
                mask ^= low
        return weights

    def exact(self, node_budget: int) -> Optional[Dict[Cell, float]]:
        """Все расстановки перебором; None — их слишком много для бюджета."""
        sizes, placements, hits = self.sizes, self.placements, self.hits
        per_placement: Dict[int, float] = {}
        stack: List[int] = []
        nodes = [0]

        def rec(i: int, blocked: int, covered: int, start: int) -> bool:
            nodes[0] += 1
            if nodes[0] > node_budget:
                return False
            if i == len(sizes):
                if covered & hits == hits:
                    for mask in stack:
                        per_placement[mask] = per_placement.get(mask, 0.0) + 1
                return True
            size = sizes[i]
            options = placements[size]
            for j in range(start, len(options)):
                mask, halo = options[j]
                if mask & blocked:
                    continue
                new_covered = covered | mask
                # раненая клетка рядом с кораблём, но не в нём — её уже никто не накроет
                if hits & (blocked | halo) & ~new_covered:
                    continue
                stack.append(mask)
                nxt = j + 1 if i + 1 < len(sizes) and sizes[i + 1] == size else 0
                ok = rec(i + 1, blocked | halo, new_covered, nxt)
                stack.pop()
                if not ok:
                    return False
            return True

        if not rec(0, 0, 0, 0):
            return None
        return self._to_cells(per_placement)

    def sampled(self, rng: random.Random) -> Dict[Cell, float]:
        """Сэмплирование с весами: сначала корабли, накрывающие раненые клетки (по одной,
        начиная с первой ненакрытой), потом остальные от больших к маленьким. Вес расстановки —
        произведение числа вариантов на каждом шаге: так оценка не смещена."""
        per_mask: Dict[int, float] = {}
        deadline = time.monotonic() + SAMPLE_SECONDS
        tries = good = 0
        while good < SAMPLE_MAX and (good < SAMPLE_MIN or time.monotonic() < deadline):
            tries += 1
            if tries > SAMPLE_MAX * 50:
                break
            result = self._sample(rng)
            if result is None:
                continue
            good += 1
            weight, masks, last = result
            # последний корабль — во всех допустимых местах сразу: оценка заметно точнее
            for mask in masks:
                per_mask[mask] = per_mask.get(mask, 0.0) + weight * len(last)
            for mask in last:
                per_mask[mask] = per_mask.get(mask, 0.0) + weight
        return self._to_cells(per_mask)

    def _sample(self, rng: random.Random) -> Optional[Tuple[float, List[int], List[int]]]:
        """Одна расстановка без последнего корабля: (вес, корабли, все места последнего)."""
        hits = self.hits
        remaining = Counter(self.sizes)
        blocked = covered = 0
        masks: List[int] = []
        weight = 1.0
        left = len(self.sizes)
        while hits & ~covered:
            target = (hits & ~covered) & -(hits & ~covered)
            options = [(size, mask, halo) for size in remaining if remaining[size] > 0
                       for mask, halo in self.placements[size]
                       if mask & target and not mask & blocked
                       and not hits & (blocked | halo) & ~(covered | mask)]
            if not options:
                return None
            left -= 1
            if left == 0:
                # последний корабль обязан накрыть все оставшиеся раненые клетки
                last = [mask for _, mask, _ in options if not hits & ~(covered | mask)]
                return (weight, masks, last) if last else None
            weight *= len(options)
            size, mask, halo = rng.choice(options)
            remaining[size] -= 1
            blocked |= halo
            covered |= mask
            masks.append(mask)
        divisor = 1
        for size in sorted(remaining, reverse=True):
            divisor *= factorial(remaining[size])
        weight /= divisor
        for size in sorted(remaining, reverse=True):
            for _ in range(remaining[size]):
                options = [mask_halo for mask_halo in self.placements[size] if not mask_halo[0] & blocked]
                if not options:
                    return None
                left -= 1
                if left == 0:
                    return weight, masks, [mask for mask, _ in options]
                weight *= len(options)
                mask, halo = rng.choice(options)
                blocked |= halo
                covered |= mask
                masks.append(mask)
        return weight, masks, [0]

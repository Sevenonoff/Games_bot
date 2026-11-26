"""«⚓ Кораблики»: генератор поля, расписание выпуска, судья и партия (только Mini App).

ТЗ — docs/boats/tz.md. Коротко: из бухты по каналам-дереву выплывают цветные кораблики, игрок
переключает развилки, чтобы каждый приплыл к причалу своего цвета. Партия — GAME_MS в реальном
времени: клиент двигает кораблики сам по тем же формулам, а сервер принимает журнал переключений
и считает итог функцией judge(). Уровень игрок выбирает из открытых; партия с точностью
≥ UNLOCK_SHARE открывает следующий. Уровни не закрываются, штрафа за новый день нет.

Таймеры (отсчёт → игра → итог) запускает Manager (_run_boats), сессия только хранит состояние.
"""
import bisect
import logging
import math
import random
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from .scoring import format_multiplier, tap_points
from .sessions import Session
from .texts import TITLES, t
from .ui import Button, Screen, data

logger = logging.getLogger(__name__)

# --- константы: пользователь может их подбирать (tz.md §5.4) ---

GAME = "boats"
# уровень: (причалов, столбцов, строк, корабликов в группе, интервал в группе мс, пауза после группы мс)
LEVELS: Dict[int, Tuple[int, int, int, int, int, int]] = {
    1: (3, 4, 5, 1, 0, 6000),
    2: (4, 4, 5, 1, 0, 5700),
    3: (5, 4, 6, 2, 3400, 7400),
    4: (6, 4, 6, 2, 3200, 7000),
    5: (7, 5, 6, 2, 3000, 6600),
    6: (8, 5, 6, 2, 2800, 6200),
    7: (9, 5, 6, 3, 2600, 7400),
    8: (10, 5, 7, 3, 2400, 6900),
    9: (11, 5, 7, 3, 2200, 6400),
    10: (12, 5, 7, 3, 2000, 5900),
    11: (13, 5, 7, 3, 1900, 5500),
    12: (14, 5, 7, 4, 1800, 6200),
    13: (14, 5, 7, 4, 1700, 5700),
    14: (14, 5, 7, 4, 1600, 5400),
    15: (14, 5, 7, 4, 1600, 4800),
}
MAX_LEVEL = max(LEVELS)
UNLOCK_SHARE = 0.9          # точность партии, с которой открывается следующий уровень
UNLOCK_MIN_ARRIVED = 10     # меньше прибытий — уровень не открывается
# палитра: (название, парус, корпус); причалы уровня получают первые N цветов
PALETTE: Tuple[Tuple[str, str, str], ...] = (
    ("красный", "#E53935", "#E53935"),
    ("синий", "#1E88E5", "#1E88E5"),
    ("жёлтый", "#FDD835", "#FDD835"),
    ("зелёный", "#43A047", "#43A047"),
    ("белый", "#FAFAFA", "#FAFAFA"),
    ("чёрный", "#212121", "#212121"),
    ("фиолетовый", "#8E24AA", "#8E24AA"),
    ("красный с белым", "#E53935", "#FAFAFA"),
    ("синий с жёлтым", "#1E88E5", "#FDD835"),
    ("зелёный с чёрным", "#43A047", "#212121"),
    ("фиолетовый с жёлтым", "#8E24AA", "#FDD835"),
    ("белый с синим", "#FAFAFA", "#1E88E5"),
    ("чёрный с красным", "#212121", "#E53935"),
    ("жёлтый с зелёным", "#FDD835", "#43A047"),
)
MS_PER_CELL = 2000          # кораблик проходит клетку за 2 с (0,5 клетки/с), на всех уровнях
GAME_MS = 120_000           # длина партии
FIRST_BOAT_MS = 500         # первый кораблик выходит через 0,5 с после начала игры
COUNTDOWN_MS = 3000         # отсчёт перед игрой: поле видно, корабликов нет
END_GRACE_MS = 1500         # после конца ждём запоздавшие нажатия, потом считаем итог
CLOCK_TOLERANCE_MS = 1500   # время нажатия по часам клиента берём, если оно не дальше этого от серверного
BRANCH_BIAS = 0.6           # генератор: как охотно даём второго потомка узлу, у которого уже есть один
FILL_TARGET = 0.85          # генератор: доля занятых клеток, до которой укорачиваются хвосты каналов
MAX_TRIES = 500             # генератор: попыток на зерно

assert len(PALETTE) >= max(n for n, *_ in LEVELS.values())

COUNTDOWN, PLAY, OVER = "countdown", "play", "over"

Cell = Tuple[int, int]
SIDES = ("N", "E", "S", "W")                     # по часовой стрелке
STEP = {"N": (-1, 0), "E": (0, 1), "S": (1, 0), "W": (0, -1)}


def side(a: Cell, b: Cell) -> str:
    """Сторона клетки a, через которую она граничит с соседней клеткой b."""
    return next(s for s, (dr, dc) in STEP.items() if (a[0] + dr, a[1] + dc) == b)


def clockwise_after(entry: str) -> List[str]:
    """Стороны по часовой стрелке, начиная со следующей за стороной входа."""
    i = SIDES.index(entry)
    return [SIDES[(i + k) % 4] for k in range(1, 4)]


# --- поле ---

@dataclass
class Field:
    level: int
    rows: int
    cols: int
    bay: Cell
    parent: Dict[Cell, Optional[Cell]]
    children: Dict[Cell, List[Cell]]          # у развилки — в порядке её выходов (out)
    colors: Dict[Cell, int]                   # причал → цвет
    init: Dict[Cell, int]                     # развилка → начальное положение (индекс в out)
    dist: Dict[Cell, int] = field(default_factory=dict)   # d(x): номер клетки на маршруте от бухты
    tries: int = 1

    def __post_init__(self):
        if not self.dist:
            self.dist = {self.bay: 0}
            order = [self.bay]
            for x in order:
                for y in self.children[x]:
                    self.dist[y] = self.dist[x] + 1
                    order.append(y)

    @property
    def piers(self) -> List[Cell]:
        return sorted(self.colors)

    @property
    def switches(self) -> List[Cell]:
        return sorted(self.init)

    @property
    def n(self) -> int:
        return len(self.colors)

    def kind(self, x: Cell) -> str:
        if x == self.bay:
            return "bay"
        if x in self.colors:
            return "pier"
        return "switch" if len(self.children[x]) == 2 else "canal"

    def switches_on_way(self, x: Cell) -> int:
        """Сколько развилок на пути от бухты до клетки x (не считая её саму)."""
        k, y = 0, self.parent[x]
        while y is not None:
            k += len(self.children[y]) == 2
            y = self.parent[y]
        return k

    def cells(self, state: Optional[Dict[Cell, int]] = None) -> List[dict]:
        """Занятые клетки для view (tz.md §6.2), по порядку (r, c). state — текущие положения развилок."""
        out = []
        for x in sorted(self.parent):
            r, c = x
            kind = self.kind(x)
            cell: dict = {"r": r, "c": c, "k": kind}
            if kind != "bay":
                cell["in"] = side(x, self.parent[x])
            if kind != "pier":
                cell["out"] = [side(x, y) for y in self.children[x]]
            if kind == "switch":
                cell["state"] = (state or self.init)[x]
                cell["init"] = self.init[x]
            if kind == "pier":
                cell["color"] = self.colors[x]
            out.append(cell)
        return out


class _Fail(Exception):
    pass


def max_switches(n: int) -> int:
    """Предел развилок на пути к любому причалу: для 14 причалов — 7, как в образце."""
    return math.ceil(math.log2(n)) + 3


def _try_generate(level: int, rng: random.Random) -> Field:
    """Одна попытка по tz.md §5.2: покрывающее дерево с ≤ 2 потомками, срезка листьев до N,
    укорачивание хвостов, проверки, раздача цветов и начальных положений."""
    n, cols, rows = LEVELS[level][:3]

    def inside(x: Cell) -> bool:
        return 0 <= x[0] < rows and 0 <= x[1] < cols

    edge = [(0, c) for c in range(cols)] + [(rows - 1, c) for c in range(cols)]
    edge += [(r, 0) for r in range(1, rows - 1)] + [(r, cols - 1) for r in range(1, rows - 1)]
    bay = rng.choice(edge)
    parent: Dict[Cell, Optional[Cell]] = {bay: None}
    children: Dict[Cell, List[Cell]] = {bay: []}
    cap = {bay: 1}

    def inward(q: Cell) -> bool:
        """Из бухты канал идёт только внутрь поля, а не вдоль края."""
        (br, bc), (qr, qc) = bay, q
        return ((br == 0 and qr == 1) or (br == rows - 1 and qr == rows - 2)
                or (bc == 0 and qc == 1) or (bc == cols - 1 and qc == cols - 2))

    frontier: List[Tuple[Cell, Cell]] = []

    def push(p: Cell) -> None:
        for dr, dc in STEP.values():
            q = (p[0] + dr, p[1] + dc)
            if inside(q) and q not in parent:
                frontier.append((p, q))

    # 1–2. рост покрывающего дерева со случайного ребра фронта
    push(bay)
    while frontier:
        i = rng.randrange(len(frontier))
        if rng.random() < BRANCH_BIAS:
            # охотнее даём второго потомка тому, у кого уже есть один: так набирается N листьев
            half = [j for j, (p, q) in enumerate(frontier)
                    if q not in parent and len(children[p]) == 1 and cap[p] == 2]
            if half:
                i = rng.choice(half)
        p, q = frontier[i]
        frontier[i] = frontier[-1]
        frontier.pop()
        if q in parent or len(children[p]) >= cap[p] or (p == bay and not inward(q)):
            continue
        parent[q], children[q] = p, []
        children[p].append(q)
        cap[q] = 1 if p == bay else 2       # первая клетка после бухты — всегда канал
        push(q)

    def leaves() -> List[Cell]:
        return [x for x in parent if not children[x] and x != bay]

    def depth(x: Cell) -> int:              # развилок на пути от бухты до x, включая её саму
        k = 0
        while x is not None:
            k += len(children[x]) == 2
            x = parent[x]
        return k

    def remove(x: Cell) -> None:
        p = parent.pop(x)
        children.pop(x)
        children[p].remove(x)

    # 3. срезка листьев до N: у развилок, глубокие ветки — охотнее
    while True:
        lv = leaves()
        if len(lv) <= n:
            break
        at_fork = [x for x in lv if len(children[parent[x]]) == 2]
        if not at_fork:
            remove(rng.choice(lv))
            continue
        remove(rng.choices(at_fork, [1 + depth(x) ** 2 for x in at_fork])[0])
    if len(leaves()) != n:
        raise _Fail

    # 4. укорачивание хвостов: причал подтягивается ближе, освободившиеся клетки — декор
    while len(parent) > FILL_TARGET * rows * cols:
        tails = [x for x in leaves() if len(children[parent[x]]) == 1 and parent[x] != bay]
        if not tails:
            break
        remove(rng.choice(tails))

    # 5. проверки годности
    piers = leaves()
    switches = [x for x in parent if len(children[x]) == 2]
    if len(piers) != n or len(switches) != n - 1:
        raise _Fail
    if len(children[children[bay][0]]) != 1:
        raise _Fail                         # до первой развилки ≥ 2 клеток: время рассмотреть кораблик
    if max(depth(x) for x in piers) > max_switches(n):
        raise _Fail

    # 6. раздача: выходы развилок по часовой стрелке, цвета причалов, начальные положения
    for x in switches:
        order = clockwise_after(side(x, parent[x]))
        children[x].sort(key=lambda y: order.index(side(x, y)))
    colors = list(range(n))
    rng.shuffle(colors)
    return Field(level, rows, cols, bay, parent, children,
                 colors=dict(zip(sorted(piers), colors)),
                 init={x: rng.randint(0, 1) for x in sorted(switches)})


def generate(level: int, seed: str) -> Field:
    """Поле уровня по зерну; детерминировано в пределах версии Python."""
    for k in range(MAX_TRIES):
        try:
            f = _try_generate(level, random.Random(f"{seed}:{k}"))
        except _Fail:
            continue
        f.tries = k + 1
        return f
    logger.error("boats: поле уровня %s не вышло за %s попыток, зерно %r — беру другое", level, MAX_TRIES, seed)
    return generate(level, f"{seed}!")


# --- расписание ---

@dataclass(frozen=True)
class Boat:
    id: int
    t: int          # момент выхода из бухты, мс от начала игры
    color: int


def schedule(level: int, seed: str, game_ms: int = GAME_MS) -> List[Boat]:
    """Выпуск группами по таблице уровня (время не случайное); цвет случайный, не три одинаковых подряд."""
    n, _, _, group, inner, pause = LEVELS[level]
    rng = random.Random(f"{seed}:sched")
    out: List[Boat] = []
    t_ms = FIRST_BOAT_MS
    while t_ms < game_ms:
        color = rng.randrange(n)
        while len(out) >= 2 and out[-1].color == color and out[-2].color == color:
            color = rng.randrange(n)
        out.append(Boat(len(out), t_ms, color))
        t_ms += pause if len(out) % group == 0 else inner
    return out


# --- судья ---

Toggle = Tuple[int, int, int]                       # (t мс, r, c)
Arrival = Tuple[int, int, int, int, bool]           # (t_arr, boat_id, r, c, верно)


def enter_ms(f: Field, boat_t: int, x: Cell) -> int:
    """Момент, когда кораблик, вышедший в boat_t, входит в клетку x: тогда фиксируется выход развилки."""
    return boat_t + (2 * f.dist[x] - 1) * MS_PER_CELL // 2


def judge(f: Field, boats: Sequence[Boat], toggles: Sequence[Toggle], game_ms: int = GAME_MS) -> List[Arrival]:
    """Прибытия к причалам до конца партии по tz.md §3.2, по порядку (t_arr, boat_id).
    Положение развилки при входе кораблика — начальное плюс число её переключений с t ≤ t_enter."""
    flips: Dict[Cell, List[int]] = {}
    for t_ms, r, c in toggles:
        if (r, c) in f.init:
            flips.setdefault((r, c), []).append(t_ms)
    for times in flips.values():
        times.sort()
    out: List[Arrival] = []
    for b in boats:
        x = f.bay
        while f.children[x]:
            ch = f.children[x]
            if len(ch) == 1:
                x = ch[0]
                continue
            n = bisect.bisect_right(flips.get(x, []), enter_ms(f, b.t, x))
            x = ch[(f.init[x] + n) % 2]
        t_arr = b.t + f.dist[x] * MS_PER_CELL
        if t_arr <= game_ms:
            out.append((t_arr, b.id, x[0], x[1], f.colors[x] == b.color))
    out.sort()
    return out


def route(f: Field, pier: Cell) -> List[Tuple[Cell, int]]:
    """Развилки на пути от бухты к причалу и нужный выход каждой."""
    path, y = [], pier
    while f.parent[y] is not None:
        p = f.parent[y]
        if len(f.children[p]) == 2:
            path.append((p, f.children[p].index(y)))
        y = p
    return path[::-1]


def perfect_toggles(f: Field, boats: Sequence[Boat], lead_ms: int = 300, game_ms: int = GAME_MS) -> List[Toggle]:
    """План идеального игрока: каждая развилка ставится как надо за lead_ms до входа кораблика.
    Нажатия после конца партии в план не входят (сервер их не примет)."""
    pier_of = {color: x for x, color in f.colors.items()}
    events = sorted((enter_ms(f, b.t, sw), sw, idx) for b in boats for sw, idx in route(f, pier_of[b.color]))
    state, last, out = dict(f.init), {}, []
    for t_enter, sw, idx in events:
        if state[sw] != idx:
            t_ms = max(t_enter - lead_ms, last.get(sw, -1) + 1)
            out.append((t_ms, sw[0], sw[1]))
            state[sw] = idx
        last[sw] = t_enter
    return sorted(x for x in out if x[0] <= game_ms)


def points(level: int, arrivals: Sequence[Arrival]) -> Tuple[int, int]:
    """Очки за прибытия по порядку и текущая серия верных: те же tap_points, что у других игр."""
    score = streak = 0
    for *_, ok in arrivals:
        if ok:
            score += tap_points(level, streak)
            streak += 1
        else:
            streak = 0
    return score, streak


def unlocks(correct: int, arrived: int) -> bool:
    """Партия открывает следующий уровень: ≥ 90% верных и хотя бы 10 прибытий."""
    return arrived >= UNLOCK_MIN_ARRIVED and correct >= UNLOCK_SHARE * arrived - 1e-9


# --- экраны вне партии ---

def colors_view(n: int) -> List[dict]:
    return [{"id": i, "name": name, "sail": sail, "hull": hull} for i, (name, sail, hull) in enumerate(PALETTE[:n])]


def only_in_app_screen() -> Screen:
    return Screen(t("boats_only_app"), [[Button(t("btn_menu"), "menu")]])


def levels_screen(storage, platform: str, uid: int) -> Screen:
    """Выбор уровня (tz.md §6.2): открытые нажимаются, закрытые — с 🔒, самый высокий открытый — «▶»."""
    opened = storage.load_progress(platform, uid, GAME).level
    best = storage.boats_best(platform, uid)
    buttons = []
    for level in sorted(LEVELS):
        if level > opened:
            buttons.append(Button(f"🔒 {level}", data("bl", level)))
            continue
        label = f"▶ {level}" if level == opened else str(level)
        if level in best:
            label += f" · ✔ {best[level][0]}/{best[level][1]}"
        buttons.append(Button(label, data("new", GAME, level)))
    rows = [buttons[i:i + 3] for i in range(0, len(buttons), 3)]
    return Screen(t("boats_levels"), rows + [[Button(t("btn_menu"), "menu")]])


def locked_note(level: int) -> str:
    return t("boats_locked", level=level - 1)


# --- партия ---

class BoatsSession(Session):
    """Партия «Корабликов»: отсчёт COUNTDOWN_MS → игра game_ms → END_GRACE_MS на запоздавшие нажатия → итог.

    progress.level — самый высокий открытый уровень; уровень партии (self.level) выбирает игрок,
    в начале партии progress не меняется. Сервер хранит журнал переключений и считает итог по нему.
    """
    game = GAME

    def __init__(self, sid, player, storage, rng, clock, *, level: int, game_ms: int = GAME_MS):
        self._chosen = level
        super().__init__(sid, player, storage, rng, clock)
        self.game_ms = game_ms
        self.seed = f"{rng.getrandbits(64):016x}"
        self.field = generate(level, self.seed)
        self.boats = schedule(level, self.seed, game_ms)
        self.toggles: List[Toggle] = []
        self.phase = COUNTDOWN
        self.started_at = clock()                  # начало отсчёта
        self.play_started_at: Optional[float] = None
        self.timers_pending = True                 # Manager ещё не запустил отсчёт и конец партии
        self.unlocked = False                      # эта партия открыла следующий уровень
        self.result: Optional[Tuple[int, int]] = None   # (верно, прибыло) записанной партии

    def _start_level(self) -> int:
        return self._chosen                        # без start_partia: нет штрафа за новый день

    # --- время ---

    def begin_play(self) -> None:
        self.phase = PLAY
        self.play_started_at = self.clock()

    def elapsed_ms(self) -> int:
        if self.play_started_at is None:
            return 0
        return max(0, round((self.clock() - self.play_started_at) * 1000))

    def time_is_up(self) -> bool:
        return self.play_started_at is not None and self.elapsed_ms() >= self.game_ms

    # --- нажатия ---

    def toggle(self, r: int, c: int, t_client: Optional[str]) -> bool:
        """Переключение развилки (tz.md §6.3). Пропускается вне игры, не на развилке, с нецелым временем
        и после конца партии. Время клиента берётся, если оно близко к серверному; журнал не убывает."""
        if self.phase != PLAY or (r, c) not in self.field.init:
            return False
        t_srv = self.elapsed_ms()
        if t_client is None:
            t_ms = t_srv
        else:
            try:
                t_ms = int(t_client)
            except ValueError:
                return False
            if abs(t_ms - t_srv) > CLOCK_TOLERANCE_MS:
                t_ms = t_srv
        if self.toggles:
            t_ms = max(t_ms, self.toggles[-1][0])
        if t_ms < 0 or t_ms > self.game_ms:
            return False
        self.toggles.append((t_ms, r, c))
        self.last_activity = self.clock()
        return True

    def tap(self, r: int, c: int) -> Optional[str]:
        self.toggle(r, c, None)
        return None

    # --- состояние ---

    def state_now(self) -> Dict[Cell, int]:
        """Положения развилок с учётом всех принятых переключений."""
        state = dict(self.field.init)
        for _, r, c in self.toggles:
            state[(r, c)] ^= 1
        return state

    def arrivals(self, until_ms: Optional[int] = None) -> List[Arrival]:
        done = judge(self.field, self.boats, self.toggles, self.game_ms)
        return done if until_ms is None else [a for a in done if a[0] <= until_ms]

    def view(self) -> dict:
        elapsed = self.elapsed_ms() if self.phase != COUNTDOWN else 0
        arrived = self.arrivals(elapsed) if self.phase != COUNTDOWN else []
        score, streak = points(self.level, arrived)
        phase = OVER if self.phase == PLAY and self.time_is_up() else self.phase
        countdown = max(0, COUNTDOWN_MS - round((self.clock() - self.started_at) * 1000))
        return {
            "kind": GAME, "title": TITLES[GAME], "level": self.level, "score": score,
            "combo": format_multiplier(streak),
            "phase": phase,
            "countdown_ms": countdown if self.phase == COUNTDOWN else 0,
            "clock": {"elapsed_ms": min(elapsed, self.game_ms), "total_ms": self.game_ms},
            "ms_per_cell": MS_PER_CELL,
            "grid": {"rows": self.field.rows, "cols": self.field.cols},
            "cells": self.field.cells(self.state_now()),
            "colors": colors_view(self.field.n),
            "boats": [{"id": b.id, "t": b.t, "color": b.color} for b in self.boats],
            "toggles": [list(x) for x in self.toggles],
            "tally": {"correct": sum(a[4] for a in arrived), "arrived": len(arrived)},
            "actions": {"tap": data("t", self.sid, "{r}", "{c}", "{t}"), "quit": data("q", self.sid)},
        }

    def screen(self) -> Screen:
        """Экран партии: в Mini App его рисует компонент по view; текст — запасной."""
        v = self.view()
        if v["phase"] == COUNTDOWN:
            line = t("boats_countdown")
        elif v["phase"] == OVER:
            line = t("boats_time_up")
        else:
            line = t("boats_hint")
        text = "\n".join([
            f"<b>{TITLES[GAME]}</b> · {t('level', level=self.level)}",
            t("boats_tally", correct=v["tally"]["correct"], arrived=v["tally"]["arrived"]),
            "", line])
        return Screen(text, [self._quit_row()], view=v)

    # --- конец ---

    def quit(self) -> Screen:
        """«Закончить» до конца: ничего не записывается, уровни не меняются (tz.md §3.4, п. 4)."""
        self.finished = True
        return levels_screen(self.storage, self.player.platform, self.player.user_id)

    def abandon(self) -> None:
        """Ушёл на другой экран: до конца времени — как «Закончить», после — итог записывается."""
        if self.time_is_up():
            self.finish()
        else:
            self.finished = True

    def _store(self, score: Optional[int], now: float) -> bool:
        correct, arrived = self.result
        p = self.player
        return self.storage.save_boats(p.platform, p.user_id, self.progress, score, self.level,
                                       correct, arrived, now)

    def finish(self) -> Screen:
        """Итог по журналу сервера: очки, рекорд, открытие уровня, путь и серия."""
        self.finished = True
        self.phase = OVER
        done = self.arrivals()
        correct, arrived = sum(a[4] for a in done), len(done)
        self.score = points(self.level, done)[0]
        self.result = (correct, arrived)
        if unlocks(correct, arrived) and self.level == self.progress.level and self.level < MAX_LEVEL:
            self.progress.level += 1
            self.progress.last_success_level = self.progress.level
            self.unlocked = True
        is_record = self._save(self.score)
        share = round(100 * correct / arrived) if arrived else 0
        lines = [t("result_title", title=TITLES[GAME]),
                 t("boats_result", level=self.level, correct=correct, arrived=arrived, share=share)]
        if self.unlocked:
            lines.append(t("boats_unlocked", level=self.progress.level))
        elif self.level == self.progress.level < MAX_LEVEL:
            lines.append(t("boats_unlock_hint", share=round(UNLOCK_SHARE * 100), level=self.level + 1))
        lines.append(t("result_score", score=self.score))
        lines.append(t("result_record_new") if is_record else t("result_record", best=self.progress.best_score))
        if self.motivation_lines:
            lines += [""] + self.motivation_lines
        rows = []
        if self.unlocked:
            rows.append([Button(t("btn_boats_next", level=self.progress.level),
                                data("new", GAME, self.progress.level))])
        rows.append([Button(t("btn_again"), data("new", GAME, self.level))])
        rows.append([Button(t("btn_boats_levels"), data("new", GAME)), Button(t("btn_menu"), "menu")])
        return Screen("\n".join(lines), rows)


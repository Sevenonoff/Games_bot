"""Морской бой с другом: состояние партии и правила, без сети и таймеров.

Правила — как в Telegram-версии (sea_fight_aiogram): первым ходит пригласивший,
ход переходит после каждого выстрела, попадание +10, потопление +20; 3 пропуска
хода — техническое поражение; ручная расстановка — 3 минуты; рейтинг Elo.

Победный выстрел сразу закрывает партию: ход не переходит, и пока мигает
последний корабль, проигравший уже не может выстрелить (баг TG-версии до 1.3.1).

Бой с компьютером — та же партия: гость — сторона компьютера (AI_USER_ID, ai_level),
её корабли расставлены сразу, ходы за неё делает sea_ai по её же сетке выстрелов.

Партия целиком сериализуется в dict (to_dict/from_dict) — так она переживает
перезапуск бота. Поле 8×7, индексация (r, c), как в seafight_solo.
"""
import random
from dataclasses import dataclass, field
from typing import Any, List, Optional, Tuple

from . import seafight_solo as sea

Cell = Tuple[int, int]

WAITING, PLACING, ACTIVE, FINISHED, CANCELLED = "waiting", "placing", "active", "finished", "cancelled"
OPEN = (WAITING, PLACING, ACTIVE)

AUTO, MANUAL = "auto", "manual"
TIME_LIMITS = (0, 10, 30, 60, 300, 3600)     # секунд на ход; 0 — без лимита
PLACEMENT_SECONDS = 180
MAX_TIMEOUTS = 3
HIT_POINTS, SUNK_POINTS = 10, 20
ELO_START, ELO_K = 1000, 32

# как закончилась партия
END_SUNK, END_TIMEOUTS, END_SURRENDER = "sunk", "timeouts", "surrender"
END_CANCELLED, END_PLACEMENT_TIMEOUT = "cancelled", "placement_timeout"

AI_USER_ID = -1                        # сторона компьютера: настоящих игроков с таким id нет

CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"   # без 0/O и 1/I
CODE_LEN = 6

# ошибки ручной расстановки — ключи texts
OUT_OF_BOUNDS, OVERLAPS, TOO_CLOSE = "mp_err_bounds", "mp_err_overlaps", "mp_err_close"


def new_code(rng: random.Random) -> str:
    return "".join(rng.choice(CODE_ALPHABET) for _ in range(CODE_LEN))


def game_type(ship_set: str) -> str:
    """Таблица рейтинга: mp_full / mp_reduced."""
    return f"mp_{ship_set}"


def ai_game(ship_set: str) -> str:
    """Партия с компьютером в истории (scores): ai_full / ai_reduced."""
    return f"ai_{ship_set}"


def elo_delta(winner_rating: int, loser_rating: int, k: int = ELO_K) -> int:
    """Сколько очков рейтинга получает победитель (столько же теряет проигравший)."""
    expected = 1 / (1 + 10 ** ((loser_rating - winner_rating) / 400))
    return round(k * (1 - expected))


def neighbours(cells: List[Cell], rows: int, cols: int) -> set:
    return {(r + dr, c + dc) for r, c in cells for dr in (-1, 0, 1) for dc in (-1, 0, 1)
            if 0 <= r + dr < rows and 0 <= c + dc < cols}


# --- ручная расстановка ---

@dataclass
class Placement:
    """Корабли ставятся по очереди, от большого к маленькому.

    Нажатие ставит центр текущего корабля (горизонтально), повторное нажатие
    на ту же клетку поворачивает его; «Зафиксировать» — к следующему кораблю.
    """
    sizes: List[int]
    rows: int = sea.ROWS
    cols: int = sea.COLS
    fixed: List[List[Cell]] = field(default_factory=list)
    center: Optional[Cell] = None       # центр текущего (ещё не зафиксированного) корабля
    vertical: bool = False

    @property
    def current_size(self) -> Optional[int]:
        return self.sizes[len(self.fixed)] if len(self.fixed) < len(self.sizes) else None

    def is_complete(self) -> bool:
        return len(self.fixed) == len(self.sizes)

    def current_cells(self) -> List[Cell]:
        if self.center is None or self.current_size is None:
            return []
        return self._cells(self.center, self.vertical)

    def _cells(self, center: Cell, vertical: bool) -> List[Cell]:
        size = self.current_size
        offset = (size - 1) // 2          # чётные: центр — левая/верхняя из двух средних
        r, c = center
        if vertical:
            return [(r - offset + i, c) for i in range(size)]
        return [(r, c - offset + i) for i in range(size)]

    def fixed_cells(self) -> set:
        return {cell for ship in self.fixed for cell in ship}

    def forbidden(self) -> set:
        """Клетки вокруг зафиксированных кораблей: сюда ставить нельзя."""
        return neighbours([cell for ship in self.fixed for cell in ship], self.rows, self.cols) - self.fixed_cells()

    def _check(self, cells: List[Cell]) -> Optional[str]:
        if any(not (0 <= r < self.rows and 0 <= c < self.cols) for r, c in cells):
            return OUT_OF_BOUNDS
        if set(cells) & self.fixed_cells():
            return OVERLAPS
        if set(cells) & self.forbidden():
            return TOO_CLOSE
        return None

    def tap(self, r: int, c: int) -> Optional[str]:
        """Поставить или повернуть текущий корабль. Возвращает ключ ошибки или None."""
        if self.current_size is None:
            return None
        if self.center == (r, c):
            error = self._check(self._cells((r, c), not self.vertical))
            if error is None:
                self.vertical = not self.vertical
            return error
        error = self._check(self._cells((r, c), self.vertical))
        if error is None:
            self.center = (r, c)
        else:
            self.center = None            # как в TG: неудачная попытка убирает корабль с поля
        return error

    def fix(self) -> bool:
        cells = self.current_cells()
        if not cells or self._check(cells) is not None:
            return False
        self.fixed.append(cells)
        self.center = None
        self.vertical = False             # как в TG: каждый следующий корабль сначала горизонтальный
        return True

    def reset(self) -> None:
        self.fixed = []
        self.center = None
        self.vertical = False

    def to_dict(self) -> dict:
        return {"sizes": self.sizes, "fixed": self.fixed, "center": self.center, "vertical": self.vertical}

    @classmethod
    def from_dict(cls, d: dict) -> "Placement":
        return cls(sizes=list(d["sizes"]), fixed=[[tuple(x) for x in ship] for ship in d["fixed"]],
                   center=tuple(d["center"]) if d["center"] else None, vertical=d["vertical"])


# --- партия ---

@dataclass
class Side:
    user_id: int
    name: str
    chat_id: Optional[int] = None
    ships: List[List[Cell]] = field(default_factory=list)
    shots: List[List[str]] = field(default_factory=list)     # мои выстрелы по полю соперника
    score: int = 0
    timeouts: int = 0
    ready: bool = False
    placement: Optional[Placement] = None
    placement_deadline: Optional[float] = None
    msg_ref: Any = None                                      # сообщение партии у игрока
    rating: Optional[int] = None                             # рейтинг и изменение после партии
    rating_delta: Optional[int] = None
    journey_lines: List[str] = field(default_factory=list)   # бой с компьютером: шаги пути и серия в итоге
    next_training: Optional[str] = None                      # и следующая игра тренировки дня, если не пройдена

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["placement"] = self.placement.to_dict() if self.placement else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "Side":
        d = dict(d)
        d["ships"] = [[tuple(x) for x in ship] for ship in d["ships"]]
        d["placement"] = Placement.from_dict(d["placement"]) if d["placement"] else None
        return cls(**d)


@dataclass
class MpGame:
    code: str
    ship_set: str
    mode: str
    time_limit: int
    host: Side
    guest: Optional[Side] = None
    status: str = WAITING
    turn: Optional[int] = None            # чей ход (user_id)
    turn_no: int = 0                      # растёт при каждой смене хода — по нему таймер узнаёт «свой» ход
    turn_started_at: float = 0.0
    moves: List[dict] = field(default_factory=list)   # {"by", "r", "c", "result"}
    winner: Optional[int] = None
    end_reason: Optional[str] = None
    created_at: float = 0.0
    finished_at: Optional[float] = None
    ai_level: Optional[str] = None        # бой с компьютером: sea_ai.NORMAL / ADVANCED

    # --- стороны ---

    @property
    def sides(self) -> List[Side]:
        return [s for s in (self.host, self.guest) if s is not None]

    def side(self, user_id: int) -> Optional[Side]:
        return next((s for s in self.sides if s.user_id == user_id), None)

    def opponent(self, user_id: int) -> Optional[Side]:
        return next((s for s in self.sides if s.user_id != user_id), None)

    @property
    def sizes(self) -> List[int]:
        return sea.SHIP_SETS[self.ship_set]

    @property
    def vs_ai(self) -> bool:
        return self.ai_level is not None

    @staticmethod
    def is_ai(user_id: Optional[int]) -> bool:
        return user_id == AI_USER_ID

    @property
    def human(self) -> Side:
        """Игрок в бою с компьютером (он же host)."""
        return self.host

    # --- подключение и расстановка ---

    def join(self, guest: Side, now: float, rng: random.Random) -> None:
        self.guest = guest
        if self.mode == AUTO:
            for s in self.sides:
                s.ships = sea.generate_ships(self.sizes, rng)
                s.ready = True
            self.start(now)
        else:
            self.status = PLACING
            for s in self.sides:
                s.placement = Placement(list(self.sizes))
                s.placement_deadline = now + PLACEMENT_SECONDS

    def join_ai(self, name: str, now: float, rng: random.Random) -> None:
        """Соперник — компьютер: его корабли расставлены сразу; ручная расстановка — только у игрока."""
        self.guest = Side(AI_USER_ID, name, ships=sea.generate_ships(self.sizes, rng), ready=True)
        if self.mode == AUTO:
            self.host.ships = sea.generate_ships(self.sizes, rng)
            self.host.ready = True
            self.start(now)
        else:
            self.status = PLACING
            self.host.placement = Placement(list(self.sizes))
            self.host.placement_deadline = now + PLACEMENT_SECONDS

    def set_ready(self, user_id: int, now: float) -> bool:
        """Расстановка игрока готова; True — оба готовы и партия началась."""
        s = self.side(user_id)
        s.ships = [list(ship) for ship in s.placement.fixed]
        s.placement = None
        s.placement_deadline = None
        s.ready = True
        if all(x.ready for x in self.sides):
            self.start(now)
            return True
        return False

    def start(self, now: float) -> None:
        self.status = ACTIVE
        for s in self.sides:
            s.shots = [[sea.UNKNOWN] * sea.COLS for _ in range(sea.ROWS)]
        self.turn = self.host.user_id
        self.turn_no += 1
        self.turn_started_at = now

    # --- ход ---

    def target(self, user_id: int) -> sea.SeaBoard:
        """Поле, по которому стреляет игрок: корабли соперника и его выстрелы."""
        return sea.SeaBoard(self.opponent(user_id).ships, shots=self.side(user_id).shots)

    def fire(self, user_id: int, r: int, c: int, now: float) -> str:
        """Выстрел. Возвращает sea.MISS/HIT/SUNK/WON; IGNORED — клетка уже обстреляна."""
        board = self.target(user_id)
        result = board.fire(r, c)
        if result == sea.IGNORED:
            return result
        me = self.side(user_id)
        me.score += {sea.HIT: HIT_POINTS, sea.SUNK: SUNK_POINTS, sea.WON: SUNK_POINTS}.get(result, 0)
        self.moves.append({"by": user_id, "r": r, "c": c, "result": result})
        if result == sea.WON:
            # победа: партия закрыта сразу, ход не переходит
            self.status = FINISHED
            self.winner = user_id
            self.end_reason = END_SUNK
            self.finished_at = now
        else:
            self.pass_turn(now)
        return result

    def pass_turn(self, now: float) -> None:
        self.turn = self.opponent(self.turn).user_id
        self.turn_no += 1
        self.turn_started_at = now

    def seconds_left(self, now: float) -> Optional[float]:
        if not self.time_limit or self.status != ACTIVE:
            return None
        return max(0.0, self.turn_started_at + self.time_limit - now)

    def timeout(self, now: float) -> bool:
        """Время хода вышло: пропуск или техническое поражение. True — партия окончена."""
        late = self.side(self.turn)
        late.timeouts += 1
        if late.timeouts >= MAX_TIMEOUTS:
            self.end(self.opponent(late.user_id).user_id, END_TIMEOUTS, now)
            return True
        self.pass_turn(now)
        return False

    def end(self, winner: Optional[int], reason: str, now: float) -> None:
        self.status = FINISHED if winner is not None else CANCELLED
        self.winner = winner
        self.end_reason = reason
        self.finished_at = now

    def ship_cells_sunk_by(self, move: dict) -> List[Cell]:
        """Клетки корабля, потопленного ходом move."""
        ship = sea.SeaBoard(self.opponent(move["by"]).ships).ship_at((move["r"], move["c"]))
        return list(ship or [])

    def last_moves(self) -> List[dict]:
        return self.moves[-2:]

    # --- сериализация ---

    def to_dict(self) -> dict:
        d = dict(self.__dict__)
        d["host"] = self.host.to_dict()
        d["guest"] = self.guest.to_dict() if self.guest else None
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "MpGame":
        d = dict(d)
        d["host"] = Side.from_dict(d["host"])
        d["guest"] = Side.from_dict(d["guest"]) if d["guest"] else None
        return cls(**d)

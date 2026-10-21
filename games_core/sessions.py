"""Партии игр: состояние, обработка нажатий и экраны.

Сессия не знает про таймеры и сеть — этим занимается Manager.
"""
import html
import math
import random
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from . import matrix, memo, path, seafight_solo as sea, tower
from .progression import Progress, register_fail, register_win, start_partia
from .scoring import format_multiplier, memo_penalty, round_bonus, tap_points
from .storage import Storage
from .texts import TITLES, plural, t
from .ui import Button, Screen, data

COUNTDOWN, PREVIEW, INPUT, REVIEW = "countdown", "preview", "input", "review"
COUNTDOWN_FROM = 3        # «3, 2, 1» перед каждым показом
ROUND_SECONDS = 60
TIMER_BAR = 10            # делений в полоске таймера

MATRIX_SHOWN = "🟦"
MATRIX_HIDDEN = "⬜"
TOWER_INACTIVE = "🟨"     # клетка без числа — всегда жёлтая
TOWER_HIDDEN = "⬜"       # клетка с числом, пока оно скрыто
WRONG_CELL = "❌"         # ошибочное нажатие на разборе после ошибки
MATRIX_ANSWER = "🟩"      # на разборе: клетка из ответа, которую игрок не нашёл
TOWER_ROUNDS = 6          # башня без таймера: партия — 6 раундов
FLOOR_POINTS = 50         # этаж растущей башни за каждые 50 очков
TOWER_ART_FLOORS = 5      # столько этажей рисуем во время игры (дальше — только число)
MEMO_HIDDEN = "⬜"
PATH_EMPTY = "⬜"
PATH_GREEN = "🟩"
PATH_RED = "🟥"
PATH_STEP = "🟦"         # клетка пути игрока
PATH_ANSWER = "🟨"       # на разборе: кратчайший путь
PATH_ROUNDS = 6           # как в башне: партия — 6 раундов без таймера
SEA_SYMBOLS = {sea.UNKNOWN: "🟦", sea.SHOT_MISS: "💠", sea.SHOT_HIT: "💥", sea.SHOT_SUNK: "💢"}


@dataclass
class Player:
    platform: str
    user_id: int
    name: str
    chat_id: Optional[int] = None


class Session:
    game: str = ""
    timed = False

    def __init__(self, sid: str, player: Player, storage: Storage, rng: random.Random,
                 clock: Callable[[], float]):
        self.sid = sid
        self.player = player
        self.storage = storage
        self.rng = rng
        self.clock = clock
        self.progress: Progress = storage.load_progress(player.platform, player.user_id, self.game)
        self.level = start_partia(self.progress, clock())
        self.score = 0
        self.combo = 0
        self.over = False                 # партия закончилась сама (поле собрано, победа)
        self.finished = False             # результат сохранён
        self.msg_ref: Any = None          # id сообщения в мессенджере, ставит транспорт
        self.on_saved: Optional[Callable[[], None]] = None   # результат записан — Manager разбудит уведомления
        self.rendered_at = 0.0            # когда сообщение партии последний раз обновлялось
        self.last_activity = clock()

    # --- общее ---

    def tap(self, r: int, c: int) -> Optional[str]:
        raise NotImplementedError

    def screen(self) -> Screen:
        raise NotImplementedError

    def quit(self) -> Screen:
        return self.finish()

    def finish(self) -> Screen:
        raise NotImplementedError

    def _level_note(self, delta: int) -> Optional[str]:
        if delta > 0:
            return t("note_level_up", level=self.progress.level)
        if delta < 0:
            return t("note_level_down", level=self.progress.level)
        return None

    def _field(self, rows: int, cols: int, symbol: Callable[[int, int], str]) -> List[List[Button]]:
        return [[Button(symbol(r, c), data("t", self.sid, r, c)) for c in range(cols)]
                for r in range(rows)]

    def _quit_row(self) -> List[Button]:
        return [Button(t("btn_quit"), data("q", self.sid))]

    def _save(self, score: Optional[int]) -> bool:
        now = self.clock()
        p = self.player
        self.storage.upsert_user(p.platform, p.user_id, p.name, p.chat_id, now)
        is_record = self.storage.save_result(p.platform, p.user_id, self.game, self.progress, score, now)
        if score is not None and self.on_saved is not None:
            self.on_saved()
        return is_record

    def _result_screen(self, lines: List[str], is_record: Optional[bool]) -> Screen:
        text = [t("result_title", title=TITLES[self.game])] + lines
        if is_record is not None:
            text.append(t("result_score", score=self.score))
            text.append(t("result_record_new") if is_record
                        else t("result_record", best=self.progress.best_score))
        return Screen("\n".join(text), [
            [Button(t("btn_again"), data("new", self.game))],
            [Button(t("btn_menu"), "menu")],
        ])


class TimedSession(Session):
    """Раунды: отсчёт «3, 2, 1», показ, затем ввод; после ошибки — разбор с ответом.

    Партия ограничена временем (clock_limited: round_seconds идут только в фазе
    ввода, отсчёт, показ и разбор их не съедают) или числом раундов (rounds_limit).
    Фазы переключает Manager по таймерам.
    """
    timed = True
    clock_limited = True
    rounds_limit: Optional[int] = None
    round_cls: Any = None
    phase_key = ""
    review_key = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.round_seconds = ROUND_SECONDS if self.clock_limited else None   # Manager может заменить
        self.time_spent = 0.0                   # секунды ввода прошлых раундов
        self.input_started: Optional[float] = None
        self.round_id = 0
        self.rounds_won = 0
        self.rounds_total = 0
        self.round_pending = False              # раунд создан, Manager ещё не запустил его таймеры
        self.review_pending = False             # ошибка: Manager покажет разбор и начнёт новый раунд
        self.wrong_cell: Optional[tuple] = None
        self.phase = COUNTDOWN
        self.countdown = COUNTDOWN_FROM
        self.round = None
        self._new_round()

    def _new_round(self) -> None:
        self._pause()
        self.wrong_cell = None
        self.round = self.round_cls.generate(self.progress.level, self.rng)
        self.round_id += 1
        self.phase = COUNTDOWN
        self.countdown = COUNTDOWN_FROM
        self.round_pending = True

    def _pause(self) -> None:
        if self.input_started is not None:
            self.time_spent += self.clock() - self.input_started
            self.input_started = None

    def begin_input(self) -> None:
        self.phase = INPUT
        self.input_started = self.clock()

    def seconds_left(self) -> float:
        if self.round_seconds is None:
            return math.inf
        spent = self.time_spent
        if self.input_started is not None:
            spent += self.clock() - self.input_started
        return max(0.0, self.round_seconds - spent)

    def time_left(self) -> int:
        return math.ceil(self.seconds_left() - 1e-9)

    def time_is_up(self) -> bool:
        return self.phase == INPUT and self.seconds_left() <= 0

    def tap(self, r: int, c: int) -> Optional[str]:
        if self.phase == COUNTDOWN:
            return t("note_countdown")
        if self.phase == PREVIEW:
            return t("note_preview")
        if self.phase == REVIEW:
            return t("note_review")
        level = self.progress.level
        result = self.round.tap(r, c)
        if result == matrix.IGNORED:
            return None
        if result == matrix.MISS:
            self.combo = 0
            self.rounds_total += 1
            delta = register_fail(self.progress)
            # разбор: поле с найденными клетками и ошибочной, новый раунд начнёт Manager
            self._pause()
            self.phase = REVIEW
            self.wrong_cell = (r, c)
            self.review_pending = True
            return self._level_note(delta) or t("note_round_fail")
        self.score += tap_points(level, self.combo)
        self.combo += 1
        if result == matrix.CLEARED:
            self.score += round_bonus(level, self.round.size)
            self.rounds_won += 1
            self.rounds_total += 1
            delta = register_win(self.progress)
            if self.rounds_done():
                self.over = True
            else:
                self._new_round()
            return self._level_note(delta) or t("note_round_ok")
        return None

    def rounds_done(self) -> bool:
        return self.rounds_limit is not None and self.rounds_total >= self.rounds_limit

    def timer(self) -> str:
        if not self.clock_limited:
            current = self.rounds_total if self.phase == REVIEW else self.rounds_total + 1
            return t("round_of", n=min(current, self.rounds_limit), total=self.rounds_limit)
        left = self.time_left()
        filled = math.ceil(TIMER_BAR * left / self.round_seconds) if self.round_seconds else 0
        bar = "▓" * filled + "░" * (TIMER_BAR - filled)
        return t("timer", left=left, bar=bar)

    def header(self) -> str:
        if self.phase == COUNTDOWN:
            phase = t("phase_countdown", n=self.countdown)
        elif self.phase == PREVIEW:
            phase = t("phase_preview")
        elif self.phase == REVIEW:
            phase = self.review_line()
        else:
            phase = t(self.phase_key)
        return "\n".join([
            f"<b>{TITLES[self.game]}</b> · {t('level', level=self.progress.level)}",
            self.timer(),
            t("timed_status", score=self.score, mult=format_multiplier(self.combo)),
            *self.extra_lines(),
            "",
            phase,
        ])

    def extra_lines(self) -> List[str]:
        return []

    def review_line(self) -> str:
        return t(self.review_key)

    def screen(self) -> Screen:
        rows = self._field(self.round.rows, self.round.cols, self.cell_symbol)
        return Screen(self.header(), rows + [self._quit_row()])

    def cell_symbol(self, r: int, c: int) -> str:
        raise NotImplementedError

    def finish(self) -> Screen:
        self.finished = True
        is_record = self._save(self.score)
        return self._result_screen([
            *self.result_extra(),
            t("result_level", level=self.progress.level),
            t("result_rounds", won=self.rounds_won,
              total=self.rounds_limit if self.rounds_limit else self.rounds_total),
        ], is_record)

    def result_extra(self) -> List[str]:
        return []


class MatrixSession(TimedSession):
    game = "matrix"
    round_cls = matrix.MatrixRound
    phase_key = "phase_matrix"
    review_key = "phase_review_matrix"

    def cell_symbol(self, r: int, c: int) -> str:
        cell = (r, c)
        if cell == self.wrong_cell:
            return WRONG_CELL
        if self.phase == REVIEW and cell in self.round.targets - self.round.found:
            return MATRIX_ANSWER
        if self.phase == PREVIEW:
            return MATRIX_SHOWN if cell in self.round.targets else MATRIX_HIDDEN
        if self.phase == COUNTDOWN:
            return MATRIX_HIDDEN
        return MATRIX_SHOWN if cell in self.round.found else MATRIX_HIDDEN


class TowerSession(TimedSession):
    game = "tower"
    round_cls = tower.TowerRound
    phase_key = "phase_tower"
    review_key = "phase_review_tower"
    clock_limited = False
    rounds_limit = TOWER_ROUNDS

    def cell_symbol(self, r: int, c: int) -> str:
        n = self.round.cells.get((r, c))
        if (r, c) == self.wrong_cell:
            return WRONG_CELL if n is None else f"{WRONG_CELL}{n}"   # ошибка и правильное число клетки
        if n is None or self.phase == COUNTDOWN:
            return TOWER_INACTIVE
        # на разборе видны все числа — правильный ответ
        if self.phase in (PREVIEW, REVIEW) or self.round.is_opened((r, c)):
            return str(n)
        return TOWER_HIDDEN

    def extra_lines(self) -> List[str]:
        return tower_art(self.score, TOWER_ART_FLOORS)

    def result_extra(self) -> List[str]:
        return tower_art(self.score, TOWER_ART_FLOORS * 2)


class PathSession(TimedSession):
    game = "path"
    round_cls = path.PathRound
    phase_key = "phase_path"
    clock_limited = False
    rounds_limit = PATH_ROUNDS

    def __init__(self, *args, **kwargs):
        self.shortest_count = 0
        super().__init__(*args, **kwargs)

    def tap(self, r: int, c: int) -> Optional[str]:
        rnd, level, won = self.round, self.progress.level, self.rounds_won
        note = super().tap(r, c)
        if self.rounds_won == won or not rnd.is_shortest():
            return note
        # кратчайший путь: ещё один бонус раунда
        bonus = round_bonus(level, rnd.shortest)
        self.score += bonus
        self.shortest_count += 1
        shortest = t("note_path_shortest", bonus=bonus)
        return shortest if note == t("note_round_ok") else f"{shortest} {note}"

    def cell_symbol(self, r: int, c: int) -> str:
        """Поле видно 1 с (показ) и на разборе; в остальное время — только свой путь, путь вслепую."""
        cell, rnd = (r, c), self.round
        if cell == self.wrong_cell:
            return WRONG_CELL
        if cell in rnd.path:
            return PATH_STEP
        if self.phase not in (PREVIEW, REVIEW):
            return PATH_EMPTY
        if cell in rnd.greens:
            return PATH_GREEN
        if cell in rnd.reds:
            return PATH_RED
        if self.phase == REVIEW and cell in rnd.solution:
            return PATH_ANSWER
        return PATH_EMPTY

    def review_line(self) -> str:
        return t("phase_review_path", reason=t(f"path_miss_{self.round.miss_reason}"))

    def result_extra(self) -> List[str]:
        return [t("result_path_shortest", n=self.shortest_count, total=self.rounds_limit)]


def floors_word(n: int) -> str:
    return plural(n, "этаж", "этажа", "этажей")


def tower_art(score: int, max_floors: int) -> List[str]:
    """Растущая башня: этаж за каждые FLOOR_POINTS очков, рисуем не больше max_floors."""
    floors = max(0, score) // FLOOR_POINTS
    lines = [t("tower_height", floors=floors, word=floors_word(floors))]
    if floors:
        lines.append("🚩" if floors <= max_floors else "🚩 ⋮")
        lines += ["🧱🧱🧱"] * min(floors, max_floors)
    return lines


class MemoSession(Session):
    game = "memo"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.board = memo.MemoBoard.generate(self.progress.level, self.rng)
        self.moves = 0
        self.mismatch_id = 0              # номер несовпадения: таймер закрывает только «своё»
        self.close_pending = False        # Manager ещё не запустил таймер закрытия

    def tap(self, r: int, c: int) -> Optional[str]:
        level = self.progress.level
        result = self.board.tap(r, c)
        if result in (memo.IGNORED, memo.OPENED):
            return None
        self.moves += 1
        if result == memo.MISMATCH:
            self.combo = 0
            self.mismatch_id += 1
            self.close_pending = True
            if self.board.penalized:
                points = memo_penalty(level)
                self.score = max(0, self.score - points)
                return t("note_penalty", points=points)
            return None
        self.score += tap_points(level, self.combo)
        self.combo += 1
        if result == memo.CLEARED:
            self.over = True
        return None

    def cell_symbol(self, r: int, c: int) -> str:
        idx = r * self.board.cols + c
        return self.board.cards[idx] if self.board.is_visible(idx) else MEMO_HIDDEN

    def screen(self) -> Screen:
        text = "\n".join([
            f"<b>{TITLES[self.game]}</b> · {t('level', level=self.progress.level)}",
            t("memo_status", found=self.board.found_pairs, pairs=self.board.pairs,
              score=self.score, mult=format_multiplier(self.combo)),
            t("memo_moves", moves=self.moves, limit=self.board.moves_limit),
            "",
            t("memo_hint"),
        ])
        rows = self._field(self.board.rows, self.board.cols, self.cell_symbol)
        return Screen(text, rows + [self._quit_row()])

    def finish(self) -> Screen:
        self.finished = True
        done = self.board.found_pairs == self.board.pairs
        limit = self.board.moves_limit
        if done and self.moves <= limit:
            # поле в лимит ходов — сразу следующий уровень
            register_win(self.progress, wins_needed=1)
            line = t("result_memo_done", moves=self.moves, limit=limit)
        elif done:
            # собрано, но слишком много ходов: уровень остаётся
            line = t("result_memo_slow", moves=self.moves, limit=limit)
        else:
            register_fail(self.progress)
            line = t("result_memo_quit", found=self.board.found_pairs, pairs=self.board.pairs)
        is_record = self._save(self.score)
        return self._result_screen([line, t("result_level", level=self.progress.level)], is_record)


class SeaSession(Session):
    ship_set = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.board = sea.SeaBoard.generate(self.ship_set, self.rng)

    def tap(self, r: int, c: int) -> Optional[str]:
        result = self.board.fire(r, c)
        self.score = self.board.score
        if result == sea.WON:
            self.over = True
            return t("note_sunk")
        return {sea.MISS: t("note_miss"), sea.HIT: t("note_hit"), sea.SUNK: t("note_sunk")}.get(result)

    def ships_left(self) -> int:
        return sum(1 for ship in self.board.ships
                   if any(self.board.shots[r][c] != sea.SHOT_SUNK for r, c in ship))

    def screen(self) -> Screen:
        text = "\n".join([
            f"<b>{TITLES[self.game]}</b>",
            t("sea_status", score=self.score, ships=self.ships_left()),
            "",
            t("sea_hint"),
        ])
        rows = self._field(self.board.rows, self.board.cols,
                           lambda r, c: SEA_SYMBOLS[self.board.shots[r][c]])
        return Screen(text, rows + [self._quit_row()])

    def finish(self) -> Screen:
        self.finished = True
        if self.board.is_won():
            is_record = self._save(self.score)
            return self._result_screen([t("result_sea_won")], is_record)
        return self._result_screen([t("result_sea_quit")], None)


class SeaFullSession(SeaSession):
    game = "sea_full"
    ship_set = "full"


class SeaReducedSession(SeaSession):
    game = "sea_reduced"
    ship_set = "reduced"


GAMES = {cls.game: cls for cls in (MemoSession, MatrixSession, TowerSession, PathSession,
                                   SeaFullSession, SeaReducedSession)}


def escape(text: str) -> str:
    return html.escape(text, quote=False)

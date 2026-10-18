"""Партии игр: состояние, обработка нажатий и экраны.

Сессия не знает про таймеры и сеть — этим занимается Manager.
"""
import html
import random
from dataclasses import dataclass
from typing import Any, Callable, List, Optional

from . import matrix, memo, seafight_solo as sea, tower
from .progression import Progress, register_fail, register_win, start_partia
from .scoring import format_multiplier, memo_penalty, round_bonus, tap_points
from .storage import Storage
from .texts import TITLES, t
from .ui import Button, Screen, data

PREVIEW, INPUT = "preview", "input"

MATRIX_SHOWN = "🟦"
MATRIX_HIDDEN = "⬜"
TOWER_EMPTY = "⬜"
MEMO_HIDDEN = "⬜"
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
        return self.storage.save_result(p.platform, p.user_id, self.game, self.progress, score, now)

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
    """Раунды на время: показ на секунду, затем ввод. Партия — ROUND_SECONDS."""
    timed = True
    round_cls: Any = None
    phase_key = ""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.deadline: Optional[float] = None   # ставит Manager после показа первого раунда
        self.round_id = 0
        self.rounds_won = 0
        self.rounds_total = 0
        self.preview_pending = False
        self.phase = PREVIEW
        self.round = None
        self._new_round()

    def _new_round(self) -> None:
        self.round = self.round_cls.generate(self.progress.level, self.rng)
        self.round_id += 1
        self.phase = PREVIEW
        self.preview_pending = True

    def time_left(self) -> int:
        if self.deadline is None:
            return 60
        return max(0, int(self.deadline - self.clock() + 0.999))

    def tap(self, r: int, c: int) -> Optional[str]:
        if self.phase == PREVIEW:
            return t("note_preview")
        level = self.progress.level
        result = self.round.tap(r, c)
        if result == matrix.IGNORED:
            return None
        if result == matrix.MISS:
            self.combo = 0
            self.rounds_total += 1
            delta = register_fail(self.progress)
            self._new_round()
            return self._level_note(delta) or t("note_round_fail")
        self.score += tap_points(level, self.combo)
        self.combo += 1
        if result == matrix.CLEARED:
            self.score += round_bonus(level, self.round.size)
            self.rounds_won += 1
            self.rounds_total += 1
            delta = register_win(self.progress)
            self._new_round()
            return self._level_note(delta) or t("note_round_ok")
        return None

    def header(self) -> str:
        phase = t("phase_preview") if self.phase == PREVIEW else t(self.phase_key)
        return "\n".join([
            f"<b>{TITLES[self.game]}</b> · {t('level', level=self.progress.level)}",
            t("timed_status", score=self.score, mult=format_multiplier(self.combo), left=self.time_left()),
            "",
            phase,
        ])

    def screen(self) -> Screen:
        rows = self._field(self.round.rows, self.round.cols, self.cell_symbol)
        return Screen(self.header(), rows + [self._quit_row()])

    def cell_symbol(self, r: int, c: int) -> str:
        raise NotImplementedError

    def finish(self) -> Screen:
        self.finished = True
        is_record = self._save(self.score)
        return self._result_screen([
            t("result_level", level=self.progress.level),
            t("result_rounds", won=self.rounds_won, total=self.rounds_total),
        ], is_record)


class MatrixSession(TimedSession):
    game = "matrix"
    round_cls = matrix.MatrixRound
    phase_key = "phase_matrix"

    def cell_symbol(self, r: int, c: int) -> str:
        cell = (r, c)
        if self.phase == PREVIEW:
            return MATRIX_SHOWN if cell in self.round.targets else MATRIX_HIDDEN
        return MATRIX_SHOWN if cell in self.round.found else MATRIX_HIDDEN


class TowerSession(TimedSession):
    game = "tower"
    round_cls = tower.TowerRound
    phase_key = "phase_tower"

    def cell_symbol(self, r: int, c: int) -> str:
        n = self.round.cells.get((r, c))
        if n is None:
            return TOWER_EMPTY
        if self.phase == PREVIEW or self.round.is_opened((r, c)):
            return str(n)
        return TOWER_EMPTY


class MemoSession(Session):
    game = "memo"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.board = memo.MemoBoard.generate(self.progress.level, self.rng)
        self.moves = 0

    def tap(self, r: int, c: int) -> Optional[str]:
        level = self.progress.level
        result = self.board.tap(r, c)
        if result in (memo.IGNORED, memo.OPENED):
            return None
        self.moves += 1
        if result == memo.MISMATCH:
            self.combo = 0
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
            "",
            t("memo_hint"),
        ])
        rows = self._field(self.board.rows, self.board.cols, self.cell_symbol)
        return Screen(text, rows + [self._quit_row()])

    def finish(self) -> Screen:
        self.finished = True
        done = self.board.found_pairs == self.board.pairs
        if done:
            register_win(self.progress)
            line = t("result_memo_done", moves=self.moves)
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


GAMES = {cls.game: cls for cls in (MemoSession, MatrixSession, TowerSession,
                                   SeaFullSession, SeaReducedSession)}


def escape(text: str) -> str:
    return html.escape(text, quote=False)

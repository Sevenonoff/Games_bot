"""Мемо: найти все пары одинаковых карт."""
import math
import random
from dataclasses import dataclass, field
from typing import List, Set, Tuple

from .icons import ICONS

IGNORED, OPENED, MATCH, MISMATCH, CLEARED = "ignored", "opened", "match", "mismatch", "cleared"

# уровень: (пар, рядов, колонок); не больше 7 колонок (лимит Max) и 14 рядов;
# дальше последнего — последнее значение
MEMO_LEVELS = (
    (3, 2, 3), (4, 2, 4), (6, 3, 4), (8, 4, 4), (10, 4, 5),
    (12, 4, 6), (15, 5, 6), (18, 6, 6), (21, 6, 7), (24, 8, 6),
    (28, 8, 7), (30, 10, 6), (35, 10, 7), (42, 12, 7), (49, 14, 7),
)
# поле засчитано, если собрано не больше чем за MOVES_PER_PAIR ходов на пару
MOVES_PER_PAIR = 2.0


def memo_params(level: int) -> Tuple[int, int, int]:
    return MEMO_LEVELS[min(level, len(MEMO_LEVELS)) - 1]


def moves_limit(pairs: int) -> int:
    return math.ceil(pairs * MOVES_PER_PAIR)


@dataclass
class MemoBoard:
    rows: int
    cols: int
    cards: List[str]                                  # иконка клетки, index = r * cols + c
    matched: Set[int] = field(default_factory=set)
    seen: Set[int] = field(default_factory=set)       # карты, которые уже открывались
    face_up: List[int] = field(default_factory=list)  # открытые, но не найденные (0..2)
    first_was_seen: bool = False                      # первая карта хода открывалась раньше
    penalized: bool = False                           # последнее несовпадение — со штрафом

    @classmethod
    def generate(cls, level: int, rng: random.Random) -> "MemoBoard":
        pairs, rows, cols = memo_params(level)
        cards = rng.sample(ICONS, pairs) * 2
        rng.shuffle(cards)
        return cls(rows, cols, cards)

    @property
    def pairs(self) -> int:
        return len(self.cards) // 2

    @property
    def moves_limit(self) -> int:
        return moves_limit(self.pairs)

    @property
    def found_pairs(self) -> int:
        return len(self.matched) // 2

    def is_visible(self, idx: int) -> bool:
        return idx in self.matched or idx in self.face_up

    def close_mismatch(self) -> bool:
        """Закрыть открытую несовпавшую пару. True — было что закрывать."""
        if len(self.face_up) != 2:
            return False
        self.face_up = []
        return True

    def tap(self, r: int, c: int) -> str:
        if not (0 <= r < self.rows and 0 <= c < self.cols):
            return IGNORED
        idx = r * self.cols + c
        if idx in self.matched:
            return IGNORED
        if len(self.face_up) == 2:
            # предыдущая неудачная пара закрывается этим нажатием
            self.face_up = []
        if idx in self.face_up:
            return IGNORED

        if not self.face_up:
            self.face_up = [idx]
            self.first_was_seen = idx in self.seen
            self.seen.add(idx)
            return OPENED

        first = self.face_up[0]
        self.face_up.append(idx)
        second_was_seen = idx in self.seen
        self.seen.add(idx)
        if self.cards[first] == self.cards[idx]:
            self.matched.update((first, idx))
            self.face_up = []
            return CLEARED if len(self.matched) == len(self.cards) else MATCH
        # штраф, только если хоть одна из карт уже открывалась до этого хода
        self.penalized = self.first_was_seen or second_was_seen
        return MISMATCH

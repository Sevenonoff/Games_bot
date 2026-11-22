"""Общий движок уровней для мемо, матрицы и башни.

3 выигрыша подряд — уровень +1 (мемо: одно поле в лимит ходов), 2 ошибки — уровень -1.
Новая партия начинается с уровня, на котором закончилась прошлая
(last_success_level: последний выигрыш или заработанный/потерянный уровень);
первая партия игры в новый день (по Москве) — на 1 уровень проще, как бы долго ни длился
перерыв; партии подряд в тот же день — без штрафа.
"""
from dataclasses import dataclass
from typing import Optional

from . import days

WINS_TO_LEVEL_UP = 3
FAILS_TO_LEVEL_DOWN = 2
NEW_DAY_LEVEL_PENALTY = 1
MIN_LEVEL = 1


@dataclass
class Progress:
    level: int = 1
    win_streak: int = 0
    fail_count: int = 0
    last_success_level: int = 1
    last_played_at: Optional[float] = None
    best_score: int = 0


def start_partia(p: Progress, now: float) -> int:
    """Выставить уровень начала партии. Возвращает этот уровень."""
    level = max(MIN_LEVEL, p.last_success_level)
    if p.last_played_at is not None and days.day_key(p.last_played_at) != days.day_key(now):
        level = max(MIN_LEVEL, level - NEW_DAY_LEVEL_PENALTY)
        p.last_success_level = level
    if level != p.level:
        p.level = level
        p.win_streak = 0
        p.fail_count = 0
    return level


def register_win(p: Progress, wins_needed: int = WINS_TO_LEVEL_UP) -> int:
    """Учесть выигрыш раунда. Возвращает изменение уровня (0 или +1).

    Заработанный уровень сразу становится уровнем старта следующей партии.
    """
    p.last_success_level = p.level
    p.win_streak += 1
    if p.win_streak >= wins_needed:
        p.level += 1
        p.last_success_level = p.level
        p.win_streak = 0
        p.fail_count = 0
        return 1
    return 0


def register_fail(p: Progress) -> int:
    """Учесть ошибку. Возвращает изменение уровня (0 или -1)."""
    p.win_streak = 0
    p.fail_count += 1
    if p.fail_count >= FAILS_TO_LEVEL_DOWN:
        p.fail_count = 0
        if p.level > MIN_LEVEL:
            p.level -= 1
            p.last_success_level = min(p.last_success_level, p.level)
            return -1
    return 0

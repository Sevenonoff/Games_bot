"""Общий движок уровней для мемо, матрицы и башни.

3 выигрыша подряд — уровень +1, 2 ошибки — уровень -1.
Новая партия начинается с последнего уровня, на котором был выигрыш;
после перерыва больше 2 суток — на 3 уровня проще.
"""
from dataclasses import dataclass
from typing import Optional

WINS_TO_LEVEL_UP = 3
FAILS_TO_LEVEL_DOWN = 2
IDLE_SECONDS = 2 * 24 * 3600
IDLE_LEVEL_PENALTY = 3
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
    if p.last_played_at is not None and now - p.last_played_at > IDLE_SECONDS:
        level = max(MIN_LEVEL, level - IDLE_LEVEL_PENALTY)
        p.last_success_level = level
    if level != p.level:
        p.level = level
        p.win_streak = 0
        p.fail_count = 0
    return level


def register_win(p: Progress) -> int:
    """Учесть выигрыш раунда. Возвращает изменение уровня (0 или +1)."""
    p.last_success_level = p.level
    p.win_streak += 1
    if p.win_streak >= WINS_TO_LEVEL_UP:
        p.level += 1
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
            return -1
    return 0

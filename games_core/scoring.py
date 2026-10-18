"""Очки и множители серий. Все константы баланса — здесь."""

TAP_POINTS = 10           # за верное нажатие (или пару в мемо), умножается на уровень
ROUND_BONUS = 5           # за пройденный раунд: × уровень × число элементов
MEMO_MISS_PENALTY = 5     # за промах по уже открывавшейся карте, × уровень

# (минимальная длина серии, множитель) — от большей к меньшей
COMBO_TIERS = ((40, 4.0), (20, 3.0), (10, 2.0), (5, 1.5), (0, 1.0))


def combo_multiplier(streak: int) -> float:
    """Множитель для нажатия, перед которым было streak верных подряд."""
    for threshold, mult in COMBO_TIERS:
        if streak >= threshold:
            return mult
    return 1.0


def tap_points(level: int, streak: int) -> int:
    return round(TAP_POINTS * level * combo_multiplier(streak))


def round_bonus(level: int, items: int) -> int:
    return ROUND_BONUS * level * items


def memo_penalty(level: int) -> int:
    return MEMO_MISS_PENALTY * level


def format_multiplier(streak: int) -> str:
    m = combo_multiplier(streak)
    return f"×{m:g}"

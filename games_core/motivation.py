"""Мотивация: «Путь» (шаги и зоны) и серия дней подряд.

Всё считается заново по истории партий (таблица scores): отдельного состояния нет,
поэтому старые игроки сразу получают свой путь, а /dbg reset стирает и его.
Минус: если поменять константы, позиции всех игроков пересчитаются.

Шаги за партию (не больше DAY_STEP_CAP в день по Москве):
  +1 за партию;
  +1 за первую сегодня партию в категории (память, числа, пространство, логика);
  +1 за новый максимальный уровень в игре.
Сверх лимита: каждые STREAK_REWARD_EVERY дней серии — +STREAK_REWARD_STEPS.
Зона — около недели регулярной игры (решение пользователя): ZONE_SIZES шагов.

Серия — дни подряд по Москве хотя бы с одной партией; пропуск дня обнуляет (без заморозок).
"""
from dataclasses import dataclass, field
from datetime import date
from typing import Dict, Iterable, List, Optional, Tuple

from . import days
from .texts import days_word, steps_word, t

CATEGORIES = {
    "memo": "memory", "matrix": "memory",
    "tower": "numbers",
    "path": "space",
    "sea_full": "logic", "sea_reduced": "logic", "mp_full": "logic", "mp_reduced": "logic",
}
CATEGORY_TITLES = {
    "memory": "🧠 Память",
    "numbers": "🔢 Числа",
    "space": "🧭 Пространство",
    "logic": "♟ Логика",
}

ZONES = ("🌿 Луг", "🌲 Лес", "🌉 Река", "⛰ Горы", "🏰 Замок",
         "🌊 Море", "🏜 Пустыня", "🏔 Ледник", "🌆 Город", "🚀 Космос")
ZONE_SIZES = (25, 35, 35, 35, 35)   # дальше — по ZONE_SIZE_LATER
ZONE_SIZE_LATER = 40
DAY_STEP_CAP = 8
STREAK_REWARD_EVERY = 5
STREAK_REWARD_STEPS = 5


@dataclass(frozen=True)
class Partia:
    game: str
    level: Optional[int]
    played_at: float


@dataclass
class Journey:
    steps: int = 0
    streak: int = 0                 # дней подряд, кончая last_day
    best_streak: int = 0
    last_day: Optional[str] = None  # последний день с партией
    rewards: int = 0                # сколько раз серия дала награду
    day_steps: int = 0              # шагов за last_day (в пределах лимита)
    day_categories: set = field(default_factory=set)
    max_level: Dict[str, int] = field(default_factory=dict)

    def current_streak(self, today: str) -> int:
        """Серия на сегодня: жива, если играли сегодня или вчера."""
        if self.last_day is None:
            return 0
        gap = (date.fromisoformat(today) - date.fromisoformat(self.last_day)).days
        return self.streak if gap <= 1 else 0

    def played_on(self, today: str) -> bool:
        return self.last_day == today


def zone_size(zone: int) -> int:
    return ZONE_SIZES[zone] if zone < len(ZONE_SIZES) else ZONE_SIZE_LATER


def zone_title(zone: int) -> str:
    title = ZONES[zone % len(ZONES)]
    lap = zone // len(ZONES)
    return f"{title} {lap + 1}" if lap else title


def zone_of(steps: int) -> Tuple[int, int, int]:
    """(номер зоны с 0, шагов в ней пройдено, размер зоны)."""
    zone = 0
    while steps >= zone_size(zone):
        steps -= zone_size(zone)
        zone += 1
    return zone, steps, zone_size(zone)


def _add(j: Journey, p: Partia) -> None:
    day = days.day_key(p.played_at)
    if day != j.last_day:
        consecutive = (j.last_day is not None
                       and (date.fromisoformat(day) - date.fromisoformat(j.last_day)).days == 1)
        j.streak = j.streak + 1 if consecutive else 1
        j.best_streak = max(j.best_streak, j.streak)
        j.last_day = day
        j.day_steps = 0
        j.day_categories = set()
        if j.streak % STREAK_REWARD_EVERY == 0:
            j.rewards += 1
            j.steps += STREAK_REWARD_STEPS

    earned = 1
    category = CATEGORIES.get(p.game)
    if category is not None and category not in j.day_categories:
        j.day_categories.add(category)
        earned += 1
    if p.level is not None:
        best = j.max_level.get(p.game, 1)
        if p.level > best:
            earned += 1
        j.max_level[p.game] = max(best, p.level)
    earned = min(earned, DAY_STEP_CAP - j.day_steps)
    j.day_steps += earned
    j.steps += earned


def replay(partias: Iterable[Partia]) -> Journey:
    j = Journey()
    for p in partias:
        _add(j, p)
    return j


@dataclass
class Events:
    """Что изменила последняя партия — строки в итог партии."""
    steps: int = 0
    zones_opened: List[int] = field(default_factory=list)
    streak: Optional[int] = None        # серия выросла до этого числа (первая партия дня)
    reward: bool = False                # серия дала награду


def diff(before: Journey, after: Journey) -> Events:
    zb, za = zone_of(before.steps)[0], zone_of(after.steps)[0]
    return Events(
        steps=after.steps - before.steps,
        zones_opened=list(range(zb + 1, za + 1)),
        streak=after.streak if after.last_day != before.last_day else None,
        reward=after.rewards > before.rewards,
    )


# --- тексты ---

def menu_lines(j: Journey, today: str) -> List[str]:
    zone, step, size = zone_of(j.steps)
    lines = [t("journey_menu", zone=zone_title(zone), step=step, size=size)]
    n = j.current_streak(today)
    if not n:
        lines.append(t("streak_none"))
    elif j.played_on(today):
        lines.append(t("streak_today", n=n, word=days_word(n)))
    else:
        lines.append(t("streak_pending", n=n, word=days_word(n)))
    return lines


def result_lines(e: Events, after: Journey) -> List[str]:
    zone, step, size = zone_of(after.steps)
    lines = []
    if e.streak is not None:
        lines.append(t("streak_up", n=e.streak, word=days_word(e.streak)))
    if e.reward:
        lines.append(t("streak_reward", n=after.streak, word=days_word(after.streak), steps=STREAK_REWARD_STEPS))
    for z in e.zones_opened:
        lines.append(t("journey_zone_open", zone=zone_title(z)))
    earned = e.steps - (STREAK_REWARD_STEPS if e.reward else 0)   # награда за серию — своей строкой
    if earned:
        lines.append(t("journey_steps", n=earned, word=steps_word(earned),
                       zone=zone_title(zone), step=step, size=size))
    else:
        lines.append(t("journey_cap"))
    return lines

"""Мотивация: «Путь» (шаги и зоны), серия дней, тренировка дня, значки, итоги периода.

Всё считается заново по истории партий (таблица scores): отдельного состояния нет,
поэтому старые игроки сразу получают свой путь, а /dbg reset стирает и его.
Минус: если поменять константы, позиции всех игроков пересчитаются.

Шаги за партию (не больше DAY_STEP_CAP в день по Москве):
  +1 за партию;
  +1 за первую сегодня партию в категории (память, числа, пространство, логика);
  +1 за новый максимальный уровень в игре.
Сверх лимита: +1 за пройденную тренировку дня (3 игры из разных категорий, свой набор у каждого
игрока на каждый день); каждые STREAK_REWARD_EVERY дней серии — +STREAK_REWARD_STEPS.
Зона — около недели регулярной игры (решение пользователя): ZONE_SIZES шагов.

Серия — дни подряд по Москве хотя бы с одной партией; пропуск дня обнуляет (без заморозок).

Путь начат заново с JOURNEY_EPOCH (все игроки — на первой локации): более ранние партии считаются для серии,
уровней и значков, но шагов не дают. Монета — за каждый шаг, сундук в конце локации — ещё CHEST_COINS.
Зоны — локации, нарисованные нейросетью (locations.py); дальше них — старые зоны ZONES.
"""
import random
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Dict, Iterable, List, Optional, Set, Tuple

from . import days, locations
from .texts import TITLES, days_word, games_word, steps_word, t
from .ui import data

CATEGORIES = {
    "memo": "memory", "matrix": "memory",
    "tower": "numbers",
    "path": "space",
    "boats": "multitask",
    "ai_full": "logic", "ai_reduced": "logic", "mp_full": "logic", "mp_reduced": "logic",
    "sea_full": "logic", "sea_reduced": "logic",     # «найди корабли»: только в истории партий
}
CATEGORY_TITLES = {
    "memory": "🧠 Память",
    "numbers": "🔢 Числа",
    "space": "🧭 Пространство",
    "logic": "♟ Логика",
    "multitask": "🔀 Многозадачность",
}
# категории, общие для чата и Mini App: по ним бонус «все категории за день» и подсказка «реже всего»;
# «Многозадачность» есть только в Mini App — игроки чата не должны терять из-за неё награды
CORE_CATEGORIES = ("memory", "numbers", "space", "logic")
LEVEL_GAMES = ("memo", "matrix", "tower", "path", "boats")

ZONES = ("🌿 Луг", "🌲 Лес", "🌉 Река", "⛰ Горы", "🏰 Замок",
         "🌊 Море", "🏜 Пустыня", "🏔 Ледник", "🌆 Город", "🚀 Космос")
ZONE_SIZES = (25, 35, 35, 35, 35)   # дальше — по ZONE_SIZE_LATER
ZONE_SIZE_LATER = 40
DAY_STEP_CAP = 8
STREAK_REWARD_EVERY = 5
STREAK_REWARD_STEPS = 5

# тренировка дня: по игре из DAILY_SIZE разных категорий; морской бой — с компьютером, малый
# (засчитан любой морской бой)
DAILY_GAMES = {"memory": ("memo", "matrix"), "numbers": ("tower",), "space": ("path",), "logic": ("ai_reduced",)}
DAILY_SIZE = 3
TRAINING_STEPS = 1
DAY = 24 * 3600
# новый путь по локациям: с этого момента все начинают с первой (решение пользователя, 2026-11-20)
JOURNEY_EPOCH = datetime(2026, 11, 20, tzinfo=timezone(timedelta(hours=3))).timestamp()
CHEST_COINS = 10


@dataclass(frozen=True)
class Partia:
    game: str
    level: Optional[int]
    played_at: float


def daily_training(uid: int, day: str) -> Tuple[str, ...]:
    """Игры тренировки дня: у каждого игрока свои, на весь день одни и те же."""
    rng = random.Random(f"daily:{uid}:{day}")
    categories = rng.sample(sorted(DAILY_GAMES), DAILY_SIZE)
    return tuple(rng.choice(DAILY_GAMES[c]) for c in categories)


def play_payload(game: str) -> str:
    """Кнопка «играть» в игру из тренировки дня. Бой с компьютером начинается сразу:
    обычный, без лимита времени, набор из названия игры, автоматическая расстановка."""
    if game.startswith("ai_"):
        return data("ain", "normal", 0, game[len("ai_"):], "auto")
    return data("new", game)


def covers(game: str, item: str) -> bool:
    """Партия в game засчитана за пункт тренировки item (любой морской бой — за морской бой)."""
    return game == item or (CATEGORIES.get(item) == "logic" and CATEGORIES.get(game) == "logic")


@dataclass
class Journey:
    uid: Optional[int] = None
    steps: int = 0
    streak: int = 0                 # дней подряд, кончая last_day
    best_streak: int = 0
    last_day: Optional[str] = None  # последний день с партией
    rewards: int = 0                # сколько раз серия дала награду
    partias: int = 0
    trainings: int = 0              # пройдено тренировок дня
    all_categories_days: int = 0    # дней, когда сыграны все категории
    day_steps: int = 0              # шагов за last_day (в пределах лимита)
    day_categories: Set[str] = field(default_factory=set)
    day_games: Set[str] = field(default_factory=set)
    day_training: Tuple[str, ...] = ()
    day_training_done: bool = False
    max_level: Dict[str, int] = field(default_factory=dict)
    steps_by_day: Dict[str, int] = field(default_factory=dict)

    def current_streak(self, today: str) -> int:
        """Серия на сегодня: жива, если играли сегодня или вчера."""
        if self.last_day is None:
            return 0
        gap = (date.fromisoformat(today) - date.fromisoformat(self.last_day)).days
        return self.streak if gap <= 1 else 0

    def played_on(self, today: str) -> bool:
        return self.last_day == today

    def training(self, today: str) -> Tuple[Tuple[str, ...], List[bool]]:
        """Тренировка дня на сегодня: игры и какие из них уже сыграны."""
        games = daily_training(self.uid or 0, today)
        played = self.day_games if self.last_day == today else set()
        return games, [any(covers(g, item) for g in played) for item in games]

    def steps_since(self, day: str) -> int:
        return sum(n for d, n in self.steps_by_day.items() if d >= day)


def zone_size(zone: int) -> int:
    return ZONE_SIZES[zone] if zone < len(ZONE_SIZES) else ZONE_SIZE_LATER


def zone_title(zone: int) -> str:
    loc = locations.of_zone(zone)
    if loc is not None:
        return loc.title
    # дальше нарисованных локаций — старые зоны, начиная с Леса (Луг уже был)
    z = zone - len(locations.all_locations()) + 1 if locations.all_locations() else zone
    title = ZONES[z % len(ZONES)]
    lap = z // len(ZONES)
    return f"{title} {lap + 1}" if lap else title


def coins_earned(steps: int) -> int:
    """Монеты за путь: по одной за шаг и сундук за каждую пройденную локацию."""
    return steps + CHEST_COINS * zone_of(steps)[0]


def zone_of(steps: int) -> Tuple[int, int, int]:
    """(номер зоны с 0, шагов в ней пройдено, размер зоны)."""
    zone = 0
    while steps >= zone_size(zone):
        steps -= zone_size(zone)
        zone += 1
    return zone, steps, zone_size(zone)


def _add(j: Journey, p: Partia, epoch: float = 0.0) -> None:
    day = days.day_key(p.played_at)
    counts = p.played_at >= epoch       # до начала нового пути партии шагов не дают
    if day != j.last_day:
        consecutive = (j.last_day is not None
                       and (date.fromisoformat(day) - date.fromisoformat(j.last_day)).days == 1)
        j.streak = j.streak + 1 if consecutive else 1
        j.best_streak = max(j.best_streak, j.streak)
        j.last_day = day
        j.day_steps = 0
        j.day_categories = set()
        j.day_games = set()
        j.day_training = daily_training(j.uid, day) if j.uid is not None else ()
        j.day_training_done = False
        if j.streak % STREAK_REWARD_EVERY == 0:
            j.rewards += 1
            if counts:
                j.steps += STREAK_REWARD_STEPS
                j.steps_by_day[day] = j.steps_by_day.get(day, 0) + STREAK_REWARD_STEPS

    j.partias += 1
    earned = 1
    category = CATEGORIES.get(p.game)
    if category is not None and category not in j.day_categories:
        j.day_categories.add(category)
        earned += 1
        if category in CORE_CATEGORIES and all(c in j.day_categories for c in CORE_CATEGORIES):
            j.all_categories_days += 1
    if p.level is not None:
        best = j.max_level.get(p.game, 1)
        if p.level > best:
            earned += 1
        j.max_level[p.game] = max(best, p.level)
    earned = min(earned, DAY_STEP_CAP - j.day_steps)
    j.day_steps += earned
    j.day_games.add(p.game)
    if (j.day_training and not j.day_training_done
            and all(any(covers(g, item) for g in j.day_games) for item in j.day_training)):
        j.day_training_done = True
        j.trainings += 1
        earned += TRAINING_STEPS          # сверх лимита, как награда за серию
    if counts:
        j.steps += earned
        j.steps_by_day[day] = j.steps_by_day.get(day, 0) + earned


def replay(partias: Iterable[Partia], uid: Optional[int] = None, epoch: Optional[float] = None) -> Journey:
    """uid нужен для тренировки дня; без него она не считается. epoch — начало пути (по умолчанию JOURNEY_EPOCH)."""
    j = Journey(uid=uid)
    epoch = JOURNEY_EPOCH if epoch is None else epoch
    for p in partias:
        _add(j, p, epoch)
    return j


def journey(storage, platform: str, uid: int) -> Journey:
    return replay(storage.partias(platform, uid), uid)


# --- значки ---

@dataclass(frozen=True)
class Badge:
    key: str
    title: str
    hint: str


def _level_badges() -> List[Badge]:
    out = []
    for level, medal in ((5, "🥉"), (10, "🥈"), (15, "🥇")):
        for game in LEVEL_GAMES:
            out.append(Badge(f"{game}{level}", f"{medal} {TITLES[game]} · уровень {level}",
                             f"дойти до {level}-го уровня"))
    return out


BADGES: Tuple[Badge, ...] = (
    Badge("first", "👣 Первый шаг", "сыграть первую партию"),
    Badge("streak5", "🔥 Пять дней", "играть 5 дней подряд"),
    Badge("streak7", "📅 Неделя подряд", "играть 7 дней подряд"),
    Badge("streak30", "🗓 Месяц подряд", "играть 30 дней подряд"),
    Badge("allcat", "🌈 Разносторонний", "за один день сыграть игры всех четырёх категорий"),
    Badge("daily1", "🎯 Тренировка дня", "пройти тренировку дня"),
    Badge("daily10", "🎯 Десять тренировок", "пройти 10 тренировок дня"),
    Badge("zone3", f"🗺 {zone_title(2)}", f"дойти до третьей зоны пути — {zone_title(2)}"),
    Badge("zone5", f"🗺 {zone_title(4)}", f"дойти до пятой зоны пути — {zone_title(4)}"),
    Badge("p100", "💯 Сотня", "сыграть 100 партий"),
    Badge("mpwin", "⚔️ Победа над другом", "выиграть морской бой у друга"),
) + tuple(_level_badges())
BADGE_BY_KEY = {b.key: b for b in BADGES}


def earned_badges(j: Journey, mp_wins: int = 0) -> List[str]:
    """Ключи заработанных значков в порядке BADGES."""
    zone = zone_of(j.steps)[0]
    have = {
        "first": j.partias >= 1,
        "streak5": j.best_streak >= 5,
        "streak7": j.best_streak >= 7,
        "streak30": j.best_streak >= 30,
        "allcat": j.all_categories_days >= 1,
        "daily1": j.trainings >= 1,
        "daily10": j.trainings >= 10,
        "zone3": zone >= 2,
        "zone5": zone >= 4,
        "p100": j.partias >= 100,
        "mpwin": mp_wins >= 1,
    }
    for game in LEVEL_GAMES:
        for level in (5, 10, 15):
            have[f"{game}{level}"] = j.max_level.get(game, 1) >= level
    return [b.key for b in BADGES if have[b.key]]


# --- что изменила партия ---

@dataclass
class Events:
    """Что изменила последняя партия — строки в итог партии."""
    steps: int = 0
    zones_opened: List[int] = field(default_factory=list)
    streak: Optional[int] = None        # серия выросла до этого числа (первая партия дня)
    reward: bool = False                # серия дала награду
    training: Optional[Tuple[int, int]] = None   # партия из тренировки дня: (сыграно, всего)
    training_done: bool = False         # этой партией тренировка дня пройдена
    next_training: Optional[str] = None  # следующая несыгранная игра тренировки
    badges: List[str] = field(default_factory=list)


def diff(before: Journey, after: Journey, game: Optional[str] = None) -> Events:
    zb, za = zone_of(before.steps)[0], zone_of(after.steps)[0]
    e = Events(
        steps=after.steps - before.steps,
        zones_opened=list(range(zb + 1, za + 1)),
        streak=after.streak if after.last_day != before.last_day else None,
        reward=after.rewards > before.rewards,
        training_done=after.trainings > before.trainings,
    )
    if game is not None and after.uid is not None and after.last_day is not None:
        games, done = after.training(after.last_day)
        if any(covers(game, item) for item in games):
            e.training = (sum(done), len(games))
            e.next_training = next((g for g, d in zip(games, done) if not d), None)
    had = set(earned_badges(before))
    e.badges = [k for k in earned_badges(after) if k not in had]
    return e


# --- итоги периода: «Мой прогресс» и недельный отчёт ---

def week_start(ts: float) -> float:
    """Понедельник 00:00 по Москве той недели, в которую попадает ts."""
    start = days.day_start(ts)
    return start - days.local(start).weekday() * DAY


def week_key(ts: float) -> str:
    return days.day_key(week_start(ts))


@dataclass
class Period:
    partias: int = 0
    days: int = 0
    steps: int = 0
    by_category: Dict[str, int] = field(default_factory=dict)
    levels: Dict[str, Tuple[Optional[int], int]] = field(default_factory=dict)  # игра: (до периода, сейчас)


def period(partias: List[Partia], j: Journey, since: float) -> Period:
    out = Period(steps=j.steps_since(days.day_key(since)))
    before: Dict[str, int] = {}
    now: Dict[str, int] = {}
    played_days = set()
    for p in partias:
        if p.level is not None:
            now[p.game] = max(now.get(p.game, 1), p.level)
            if p.played_at < since:
                before[p.game] = max(before.get(p.game, 1), p.level)
        if p.played_at >= since:
            out.partias += 1
            played_days.add(days.day_key(p.played_at))
            category = CATEGORIES.get(p.game)
            if category is not None:
                out.by_category[category] = out.by_category.get(category, 0) + 1
    out.days = len(played_days)
    out.levels = {g: (before.get(g), now[g]) for g in LEVEL_GAMES if g in now}
    return out


BAR = 8


def category_lines(p: Period) -> List[str]:
    top = max(p.by_category.values(), default=0)
    lines = []
    for key, title in CATEGORY_TITLES.items():
        n = p.by_category.get(key, 0)
        filled = round(BAR * n / top) if top else 0
        if n and not filled:
            filled = 1
        lines.append(f"{title} {'▓' * filled}{'░' * (BAR - filled)} {n}")
    return lines


def level_lines(p: Period) -> List[str]:
    lines = []
    for game in LEVEL_GAMES:
        if game not in p.levels:
            lines.append(t("progress_level_none", title=TITLES[game]))
            continue
        was, now = p.levels[game]
        if was is None:
            lines.append(t("progress_level_new", title=TITLES[game], level=now))
        elif now > was:
            lines.append(t("progress_level_up", title=TITLES[game], was=was, level=now))
        else:
            lines.append(t("progress_level", title=TITLES[game], level=now))
    return lines


def weakest_category(p: Period) -> Optional[str]:
    """Категория, которую реже всего тренировали за период (подсказка в отчёте)."""
    if not p.partias:
        return None
    key = min(CORE_CATEGORIES, key=lambda k: (p.by_category.get(k, 0), CORE_CATEGORIES.index(k)))
    return CATEGORY_TITLES[key]


# --- тексты ---

def menu_lines(j: Journey, today: str, coins: Optional[int] = None) -> List[str]:
    zone, step, size = zone_of(j.steps)
    lines = [t("journey_menu", zone=zone_title(zone), step=step, size=size,
               coins=coins_earned(j.steps) if coins is None else coins)]
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
    if e.training_done:
        lines.append(t("daily_result_done"))
    elif e.training is not None:
        lines.append(t("daily_result", done=e.training[0], total=e.training[1]))
    for z in e.zones_opened:
        lines.append(t("journey_zone_open", zone=zone_title(z)))
        lines.append(t("journey_chest", n=CHEST_COINS))
    # награды за серию и тренировку дня — своими строками
    earned = e.steps - (STREAK_REWARD_STEPS if e.reward else 0) - (TRAINING_STEPS if e.training_done else 0)
    if earned:
        lines.append(t("journey_steps", n=earned, word=steps_word(earned),
                       zone=zone_title(zone), step=step, size=size))
    else:
        lines.append(t("journey_cap"))
    for key in e.badges:
        lines.append(t("badge_new", title=BADGE_BY_KEY[key].title))
    return lines


def period_summary(p: Period) -> str:
    return t("progress_summary", partias=p.partias, pword=games_word(p.partias), days=p.days,
             dword=days_word(p.days), steps=p.steps, sword=steps_word(p.steps))

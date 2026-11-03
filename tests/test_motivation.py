"""Путь и серия дней: расчёт по истории партий."""
from games_core import days
from games_core.motivation import (DAY_STEP_CAP, STREAK_REWARD_STEPS, Partia, diff, replay,
                                   zone_of, zone_title)

DAY = 24 * 3600
NOON = days.day_start(1_000_000.0) + 12 * 3600   # полдень по Москве


def at(day: int, hour: float = 0) -> float:
    return NOON + day * DAY + hour * 3600


def test_partia_category_and_level_bonus():
    j = replay([Partia("memo", 2, at(0))])
    assert j.steps == 3                     # партия + новая категория + новый уровень
    j = replay([Partia("memo", 2, at(0)), Partia("matrix", 1, at(0, 1))])
    assert j.steps == 4                     # матрица — та же категория «память»
    j = replay([Partia("memo", 1, at(0)), Partia("tower", 1, at(0, 1))])
    assert j.steps == 4                     # поездка — новая категория


def test_level_bonus_only_for_new_maximum():
    j = replay([Partia("memo", 3, at(0)), Partia("memo", 2, at(1)), Partia("memo", 3, at(2))])
    # 3 (новый уровень) + 2 (новый день: категория) + 2 (уровень 3 уже был)
    assert j.steps == 7


def test_category_bonus_resets_next_day():
    j = replay([Partia("sea_full", None, at(0)), Partia("sea_full", None, at(1))])
    assert j.steps == 4


def test_day_cap():
    j = replay([Partia("sea_full", None, at(0, h / 10)) for h in range(20)])
    assert j.steps == DAY_STEP_CAP


def test_day_boundary_is_moscow_midnight():
    midnight = days.day_start(at(1))
    j = replay([Partia("sea_full", None, midnight - 60), Partia("sea_full", None, midnight + 60)])
    assert j.streak == 2 and j.steps == 4


def test_streak_strict_and_reward():
    history = [Partia("sea_full", None, at(d)) for d in range(5)]
    j = replay(history)
    assert j.streak == 5 and j.rewards == 1
    assert j.steps == 5 * 2 + STREAK_REWARD_STEPS
    j = replay(history + [Partia("sea_full", None, at(6))])     # пропущен день 5
    assert j.streak == 1 and j.best_streak == 5


def test_current_streak_needs_today_or_yesterday():
    j = replay([Partia("memo", 1, at(0)), Partia("memo", 1, at(1))])
    assert j.current_streak(days.day_key(at(1))) == 2
    assert j.current_streak(days.day_key(at(2))) == 2
    assert j.current_streak(days.day_key(at(3))) == 0


def test_zones():
    assert zone_of(0) == (0, 0, 25)
    assert zone_of(24) == (0, 24, 25)
    assert zone_of(25) == (1, 0, 35)
    assert zone_of(25 + 35 * 4) == (5, 0, 40)
    assert zone_title(0) == "🌿 Луг"
    assert zone_title(10) == "🌿 Луг 2"


def test_zone_is_about_a_week():
    """Решение пользователя: обычные 2–3 партии в день проходят зону примерно за неделю, не за день."""
    history = []
    for d in range(30):
        history += [Partia("memo", 1, at(d)), Partia("tower", 1, at(d, 1)), Partia("memo", 1, at(d, 2))]
        if zone_of(replay(history).steps)[0] == 1:
            break
    assert 4 <= d <= 7
    history = [Partia(g, 1, at(0, i / 10)) for i, g in enumerate(["memo", "tower", "path", "sea_full"] * 10)]
    assert zone_of(replay(history).steps)[0] == 0     # за один день зону не пройти


def test_diff_events():
    before = replay([Partia("memo", 1, at(d)) for d in range(4)])
    after = replay([Partia("memo", 1, at(d)) for d in range(5)])
    e = diff(before, after)
    assert e.streak == 5 and e.reward and e.steps == 2 + STREAK_REWARD_STEPS
    same_day = replay([Partia("memo", 1, at(d)) for d in range(5)] + [Partia("memo", 1, at(4, 1))])
    e = diff(after, same_day)
    assert e.streak is None and not e.reward and e.steps == 1

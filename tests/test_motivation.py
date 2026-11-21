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
    # нарисованные нейросетью локации главы 1, дальше — старые зоны с Леса
    assert zone_title(0) == "🏡 Луг у дома"
    assert zone_title(1) == "🎃 Ферма тётушки Бурёнки"
    assert zone_title(7) == "🗼 Опушка и сторожевая башня"
    assert zone_title(8) == "🌲 Лес"
    assert zone_title(17) == "🌿 Луг 2"


def test_journey_starts_anew_at_epoch():
    """Решение пользователя: всех игроков вернули на первую локацию. Старые партии — для серии и уровней,
    но не для шагов."""
    old = [Partia("memo", 3, at(0)), Partia("tower", 2, at(1))]
    new = [Partia("memo", 3, at(2))]
    j = replay(old + new, epoch=at(2) - 60)
    assert j.steps == 2                  # партия + новая категория; уровень 3 в мемо уже был
    assert j.streak == 3 and j.partias == 3


def test_coins():
    from games_core.motivation import CHEST_COINS, coins_earned
    assert coins_earned(0) == 0
    assert coins_earned(24) == 24
    assert coins_earned(25) == 25 + CHEST_COINS
    assert coins_earned(25 + 35) == 60 + 2 * CHEST_COINS


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


# --- тренировка дня, значки, итоги периода ---

from games_core.motivation import (BADGES, CATEGORIES, DAILY_SIZE, LEVEL_GAMES, Journey, TRAINING_STEPS,  # noqa: E402
                                   covers, daily_training, earned_badges, period, week_start)


def test_daily_training_is_stable_and_varied():
    day = days.day_key(at(0))
    games = daily_training(7, day)
    assert games == daily_training(7, day) and len(games) == DAILY_SIZE
    assert len({CATEGORIES[g] for g in games}) == DAILY_SIZE          # разные категории
    sets = {daily_training(uid, day) for uid in range(30)} | {daily_training(7, days.day_key(at(d))) for d in range(30)}
    assert len(sets) > 5                                                # у игроков и по дням — разные


def test_training_bonus_and_any_sea_counts():
    assert covers("sea_full", "sea_reduced") and covers("memo", "memo") and not covers("matrix", "memo")
    # бой с компьютером заменил «найди корабли»: засчитан любой морской бой, и старые партии тоже
    assert covers("ai_full", "ai_reduced") and covers("mp_reduced", "ai_reduced") and covers("sea_full", "ai_reduced")


def test_daily_sea_starts_computer_game_at_once():
    from games_core.motivation import play_payload
    assert play_payload("ai_reduced") == "ain:normal:0:reduced:auto"
    assert play_payload("memo") == "new:memo"
    uid, day = 7, days.day_key(at(0))
    games = daily_training(uid, day)
    played = [Partia("ai_full" if g == "ai_reduced" else g, None, at(0, i)) for i, g in enumerate(games)]
    without = replay(played)                        # без uid тренировка не считается
    j = replay(played, uid)
    assert j.trainings == 1 and j.steps == without.steps + TRAINING_STEPS


def test_training_bonus_is_beyond_day_cap():
    uid, day = 7, days.day_key(at(0))
    games = daily_training(uid, day)
    filler = [Partia("sea_full", None, at(0, i / 10)) for i in range(10)]          # лимит набран
    j = replay(filler + [Partia(g, None, at(0, 2 + i)) for i, g in enumerate(games)], uid)
    assert j.steps == DAY_STEP_CAP + TRAINING_STEPS


def test_badges():
    assert len({b.key for b in BADGES}) == len(BADGES)
    assert earned_badges(Journey()) == []
    j = replay([Partia(g, 10, at(0, i)) for i, g in enumerate(["memo", "tower", "path", "sea_full"])])
    have = set(earned_badges(j))
    assert {"first", "allcat", "memo10", "memo5", "tower10", "path10"} <= have
    assert "memo15" not in have and "matrix5" not in have and "mpwin" not in have
    assert "mpwin" in earned_badges(j, mp_wins=1)
    long = replay([Partia("memo", 1, at(d)) for d in range(30)])
    assert {"streak5", "streak7", "streak30"} <= set(earned_badges(long))


def test_period_counts_levels_and_categories():
    history = [Partia("memo", 3, at(0)), Partia("memo", 5, at(8)), Partia("tower", 2, at(9)),
               Partia("sea_full", None, at(9, 1))]
    p = period(history, replay(history), days.day_start(at(7)))
    assert p.partias == 3 and p.days == 2
    assert p.by_category == {"memory": 1, "numbers": 1, "logic": 1}
    assert p.levels["memo"] == (3, 5) and p.levels["tower"] == (None, 2)
    assert set(p.levels) <= set(LEVEL_GAMES)


def test_week_starts_on_moscow_monday():
    for d in range(14):
        start = week_start(at(d))
        assert days.local(start).weekday() == 0 and days.local(start).hour == 0
        assert 0 <= at(d) - start < 7 * DAY

"""Экраны мотивации вне партии: тренировка дня, «Мой прогресс», значки, итоги недели, лига друзей.

Расчёты — в motivation.py (по истории партий), здесь — только экраны.

Payload'ы:
  day     тренировка дня
  prog    мой прогресс за 7 дней
  bdg     значки
"""
import html
from typing import TYPE_CHECKING, List

from . import days, motivation
from .sessions import Player
from .texts import TITLES, days_word, steps_word, t
from .ui import Button, Screen, data

if TYPE_CHECKING:
    from .manager import Manager

ACTIONS = ("day", "prog", "bdg")
LEAGUE_SIZE = 10
MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}


def dispatch(mgr: "Manager", player: Player, parts: List[str]) -> Screen:
    if parts[0] == "day":
        return daily_screen(mgr, player)
    if parts[0] == "bdg":
        return badges_screen(mgr, player)
    return progress_screen(mgr, player)


def mp_wins(mgr: "Manager", uid: int) -> int:
    return sum(won for _, _, won, _ in mgr.storage.ratings_of(mgr.platform, uid))


# --- тренировка дня ---

def daily_status(mgr: "Manager", uid: int, j: motivation.Journey = None):
    j = j or motivation.journey(mgr.storage, mgr.platform, uid)
    return j.training(days.day_key(mgr.clock()))


def daily_button(mgr: "Manager", uid: int, j: motivation.Journey) -> Button:
    games, done = daily_status(mgr, uid, j)
    if all(done):
        return Button(t("btn_daily_done"), "day")
    return Button(t("btn_daily", done=sum(done), total=len(games)), "day")


def daily_screen(mgr: "Manager", player: Player) -> Screen:
    games, done = daily_status(mgr, player.user_id)
    items = "\n".join(
        t("daily_item_done" if d else "daily_item", title=TITLES[g],
          category=motivation.CATEGORY_TITLES[motivation.CATEGORIES[g]])
        for g, d in zip(games, done))
    text = t("daily_title", items=items)
    rows = []
    nxt = next((g for g, d in zip(games, done) if not d), None)
    if nxt is None:
        text += "\n\n" + t("daily_all_done")
    else:
        rows.append([Button(t("btn_daily_start", title=TITLES[nxt]), motivation.play_payload(nxt))])
    return Screen(text, rows + [[Button(t("btn_menu"), "menu")]])


# --- мой прогресс и итоги недели ---

def _period_text(mgr: "Manager", uid: int, j: motivation.Journey, since: float, title: str,
                 extra: List[str] = ()) -> List[str]:
    p = motivation.period(mgr.storage.partias(mgr.platform, uid), j, since)
    today = days.day_key(mgr.clock())
    n, best = j.current_streak(today), j.best_streak
    lines = [title, "", motivation.period_summary(p), "",
             t("progress_categories"), *motivation.category_lines(p), "",
             t("progress_levels"), *motivation.level_lines(p), "",
             t("progress_streak", n=n, word=days_word(n), best=best, bword=days_word(best)) if n
             else t("progress_streak_none", best=best, bword=days_word(best)),
             t("progress_trainings", n=j.trainings), *extra]
    hint = motivation.weakest_category(p)
    if hint is not None:
        lines += ["", t("progress_hint", category=hint)]
    return lines


def progress_screen(mgr: "Manager", player: Player) -> Screen:
    uid = player.user_id
    j = motivation.journey(mgr.storage, mgr.platform, uid)
    since = days.day_start(mgr.clock()) - 6 * motivation.DAY
    badges = motivation.earned_badges(j, mp_wins(mgr, uid))
    lines = _period_text(mgr, uid, j, since, t("progress_title"),
                         [t("progress_badges", n=len(badges), total=len(motivation.BADGES))])
    return Screen("\n".join(lines), [
        [Button(t("btn_badges"), "bdg"), Button(t("btn_journey"), "jr")],
        [Button(t("btn_menu"), "menu")],
    ])


def weekly_notice(mgr: "Manager", uid: int) -> Screen:
    j = motivation.journey(mgr.storage, mgr.platform, uid)
    lines = _period_text(mgr, uid, j, motivation.week_start(mgr.clock()), t("weekly_title"))
    lines += ["", t("weekly_off_hint")]
    return Screen("\n".join(lines), [
        [Button(t("btn_progress"), "prog")],
        [Button(t("btn_menu"), "menu")],
    ])


# --- значки ---

def badges_screen(mgr: "Manager", player: Player) -> Screen:
    j = motivation.journey(mgr.storage, mgr.platform, player.user_id)
    have = set(motivation.earned_badges(j, mp_wins(mgr, player.user_id)))
    lines = [t("badges_title", n=len(have), total=len(motivation.BADGES)), ""]
    if have:
        lines.append(t("badges_earned"))
        lines += [b.title for b in motivation.BADGES if b.key in have]
    else:
        lines.append(t("badges_none"))
    locked = [b for b in motivation.BADGES if b.key not in have]
    if locked:
        lines += ["", t("badges_locked")]
        lines += [t("badge_locked", title=b.title, hint=b.hint) for b in locked]
    return Screen("\n".join(lines), [
        [Button(t("btn_back_progress"), "prog")],
        [Button(t("btn_menu"), "menu")],
    ])


# --- лига друзей ---

def league_lines(mgr: "Manager", player: Player, friend_ids: List[int]) -> List[str]:
    """Шаги на пути с понедельника у игрока и друзей, лучшие LEAGUE_SIZE."""
    monday = days.day_key(motivation.week_start(mgr.clock()))
    ids = [player.user_id] + [f for f in friend_ids if f != player.user_id]
    names = mgr.storage.names(mgr.platform, ids)
    steps = {uid: motivation.journey(mgr.storage, mgr.platform, uid).steps_since(monday) for uid in ids}
    order = sorted(ids, key=lambda uid: (-steps[uid], names.get(uid, "?").lower(), uid))
    lines = [t("league_title")]
    for place, uid in enumerate(order[:LEAGUE_SIZE], 1):
        me = uid == player.user_id
        name = html.escape(names.get(uid, player.name if me else "?"), quote=False)
        lines.append(t("league_line", place=MEDALS.get(place, f"{place}."), name=name, steps=steps[uid],
                       word=steps_word(steps[uid]), me=t("league_me") if me else ""))
    if player.user_id not in order[:LEAGUE_SIZE]:
        place = order.index(player.user_id) + 1
        lines.append(t("league_line", place=f"{place}.", name=html.escape(player.name, quote=False),
                       steps=steps[player.user_id], word=steps_word(steps[player.user_id]), me=t("league_me")))
    return lines


def friend_journey_line(mgr: "Manager", friend_id: int) -> str:
    j = motivation.journey(mgr.storage, mgr.platform, friend_id)
    zone, step, size = motivation.zone_of(j.steps)
    n = j.current_streak(days.day_key(mgr.clock()))
    return t("friend_journey", zone=motivation.zone_title(zone), step=step, size=size, n=n, word=days_word(n))

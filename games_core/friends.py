"""Друзья: постоянная ссылка-приглашение, список друзей и карточка друга.

У каждого игрока один код (friend_codes). Друг переходит по ссылке ?start=fr_<код>
(или присылает код сообщением) — и дружба записывается в обе стороны.
«Сегодня» — московские сутки (days).

Payload'ы:
  fri          пригласить друга: ссылка и код
  fr[:<стр>]   мои друзья: активность за сегодня
  frs:<id>     карточка друга: сегодня и рекорды
  frj:<код>    подружиться по ссылке
"""
import html
import math
from typing import TYPE_CHECKING, List

from . import days, progress
from .seafight_mp import CODE_ALPHABET
from .sessions import Player
from .texts import TITLES, games_word, t
from .ui import Button, Reply, Screen, data

if TYPE_CHECKING:
    from .manager import Manager

ACTIONS = ("fr", "fri", "frs", "frj")
CODE_LEN = 8               # у кода боя с другом 6 — присланные текстом коды не путаются
PAGE = 10                  # друзей на страницу: кнопка на каждого
NAME_LEN = 40              # имя на кнопке


def looks_like_code(word: str) -> bool:
    w = word.upper()
    return len(w) == CODE_LEN and all(ch in CODE_ALPHABET for ch in w) and any(ch.isdigit() for ch in w)


def escape(name: str) -> str:
    return html.escape(name, quote=False)


def menu_row() -> List[Button]:
    return [Button(t("btn_menu"), "menu")]


def friends_row() -> List[Button]:
    return [Button(t("btn_friends"), "fr")]


def dispatch(mgr: "Manager", player: Player, parts: List[str]) -> Reply:
    action, args = parts[0], parts[1:]
    if action == "fri":
        return Reply(invite_screen(mgr, player))
    if action == "frj" and args:
        return Reply(join(mgr, player, args[0].upper()))
    if action == "frs" and args and args[0].lstrip("-").isdigit():
        return Reply(friend_screen(mgr, player, int(args[0])))
    page = int(args[0]) if action == "fr" and args and args[0].isdigit() else 0
    return Reply(friends_screen(mgr, player, page))


def make_code(mgr: "Manager") -> str:
    while True:
        code = "".join(mgr.rng.choice(CODE_ALPHABET) for _ in range(CODE_LEN))
        if looks_like_code(code):
            return code


def invite_screen(mgr: "Manager", player: Player) -> Screen:
    code = mgr.storage.friend_code(mgr.platform, player.user_id, lambda: make_code(mgr))
    text = t("friend_invite", link=mgr.start_link(f"fr_{code}"), code=code)
    return Screen(text, [friends_row(), menu_row()])


def join(mgr: "Manager", player: Player, code: str) -> Screen:
    storage, platform, uid = mgr.storage, mgr.platform, player.user_id
    owner = storage.code_owner(platform, code)
    if owner is None:
        return Screen(t("friend_bad_link"), [menu_row()])
    if owner == uid:
        return Screen(t("friend_own_link"), [friends_row(), menu_row()])
    owner_name = escape(storage.names(platform, [owner]).get(owner, "?"))
    if not storage.add_friends(platform, owner, uid, mgr.clock()):
        return Screen(t("friend_already", name=owner_name), [friends_row(), menu_row()])
    # пригласившему — новое сообщение, чтобы пришло уведомление
    mgr.send_later(owner, Screen(t("friend_new", name=escape(player.name)), [friends_row(), menu_row()]))
    return Screen(t("friend_new", name=owner_name), [friends_row(), menu_row()])


def friends_screen(mgr: "Manager", player: Player, page: int = 0) -> Screen:
    storage, platform = mgr.storage, mgr.platform
    ids = storage.friends(platform, player.user_id)
    invite = [Button(t("btn_invite_friend"), "fri")]
    if not ids:
        return Screen(f"{t('friends_title')}\n\n{t('friends_empty')}", [invite, menu_row()])
    names = storage.names(platform, ids)
    today = storage.played_since(platform, ids, days.day_start(mgr.clock()))
    counts = {uid: sum(n for n, _ in today.get(uid, {}).values()) for uid in ids}
    ids.sort(key=lambda uid: (counts[uid] == 0, names.get(uid, "?").lower(), uid))

    pages = math.ceil(len(ids) / PAGE)
    page = min(page, pages - 1)
    shown = ids[page * PAGE:(page + 1) * PAGE]
    lines = [t("friends_title"), ""]
    for uid in shown:
        name, n = escape(names.get(uid, "?")), counts[uid]
        lines.append(t("friend_active", name=name, count=n, word=games_word(n)) if n
                     else t("friend_idle", name=name))
    lines += [""] + progress.league_lines(mgr, player, ids)
    rows = [[Button(f"👤 {names.get(uid, '?')[:NAME_LEN]}", data("frs", uid))] for uid in shown]
    if pages > 1:
        lines += ["", t("friends_page", page=page + 1, pages=pages)]
        nav = []
        if page > 0:
            nav.append(Button(t("btn_prev"), data("fr", page - 1)))
        if page < pages - 1:
            nav.append(Button(t("btn_next"), data("fr", page + 1)))
        rows.append(nav)
    return Screen("\n".join(lines), rows + [invite, menu_row()])


def friend_screen(mgr: "Manager", player: Player, friend_id: int) -> Screen:
    storage, platform = mgr.storage, mgr.platform
    back = [Button(t("btn_back_friends"), "fr")]
    if not storage.are_friends(platform, player.user_id, friend_id):
        return Screen(t("friend_not_found"), [back, menu_row()])
    name = escape(storage.names(platform, [friend_id]).get(friend_id, "?"))
    lines = [t("friend_card", name=name), "", progress.friend_journey_line(mgr, friend_id), ""]

    today = storage.played_since(platform, [friend_id], days.day_start(mgr.clock())).get(friend_id, {})
    total = sum(n for n, _ in today.values())
    if total:
        lines.append(t("friend_today", count=total, word=games_word(total)))
        for game, (n, best) in sorted(today.items(), key=lambda kv: game_order(kv[0])):
            lines.append(t("friend_today_game", title=TITLES.get(game, game), count=n,
                           word=games_word(n), best=best))
    else:
        lines.append(t("friend_today_none"))

    lines += ["", t("friend_records")]
    records = sorted(storage.records(platform, friend_id), key=lambda r: game_order(r[0]))
    for game, score, level in records:
        title = TITLES.get(game, game)
        lines.append(t("friend_record_sea", title=title, score=score) if game.startswith("sea_")
                     else t("friend_record", title=title, score=score, level=level))
    ratings = sorted(storage.ratings_of(platform, friend_id), key=lambda r: game_order(r[0]))
    for game_type, rating, won, lost in ratings:
        lines.append(t("friend_rating", title=TITLES.get(game_type, game_type), rating=rating, won=won, lost=lost))
    if not records and not ratings:
        lines.append(t("friend_records_none"))
    return Screen("\n".join(lines), [back, menu_row()])


def game_order(game: str) -> int:
    order = list(TITLES)
    return order.index(game) if game in order else len(order)

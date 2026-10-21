"""Настройки игрока и сообщения, которые бот присылает сам: от друзей и напоминания.

Уведомление от друзей — одно в день, с FRIEND_FROM до FRIEND_UNTIL по Москве: кто-то из друзей
сегодня уже сыграл, а игрок ещё нет. Проверка — сразу после каждой записанной партии (wake)
и раз в минуту (loop): так партия друга с утра даст уведомление ровно в 12:00.
Напоминание — в выбранный час (с запасом REMINDER_GRACE часов на перезапуск бота),
если игрок сегодня не играл. Игроку посреди партии не пишем: проверим на следующей минуте.
День отмечается до отправки — повтора не будет, даже если мессенджер ответил ошибкой.

Payload'ы настроек:
  set              экран настроек
  set:fn           уведомления от друзей вкл/выкл
  set:rm           выбор часа напоминания
  set:rm:<час|off> поставить час / выключить
"""
import html
import logging
from typing import TYPE_CHECKING, List, Tuple

from . import days
from .sessions import Player
from .texts import TITLES, t
from .ui import Button, Reply, Screen, data

if TYPE_CHECKING:
    from .manager import Manager

logger = logging.getLogger(__name__)

ACTIONS = ("set",)
TICK_SECONDS = 60
FRIEND_FROM, FRIEND_UNTIL = 12, 22      # часы по Москве, когда шлём уведомления от друзей
REMINDER_HOURS = (9, 13, 19, 21)
REMINDER_GRACE = 2                      # бот лежал в нужный час — напомним в ближайшие 2 часа
MAX_NAMES = 3                           # «Боб, Алиса, Ева и ещё 2»
TRAINING_GAMES = ("memo", "matrix", "tower", "path")


# --- настройки ---

def dispatch(mgr: "Manager", player: Player, parts: List[str]) -> Reply:
    storage, platform, uid = mgr.storage, mgr.platform, player.user_id
    args = parts[1:]
    if args[:1] == ["fn"]:
        on = storage.settings(platform, uid)["friend_notify"]
        storage.update_settings(platform, uid, friend_notify=0 if on else 1)
    elif args[:1] == ["rm"] and len(args) == 1:
        return Reply(reminder_screen(mgr, player))
    elif args[:1] == ["rm"]:
        if args[1] == "off":
            storage.update_settings(platform, uid, reminder_hour=None)
        elif args[1].isdigit() and int(args[1]) in REMINDER_HOURS:
            storage.update_settings(platform, uid, reminder_hour=int(args[1]))
    return Reply(settings_screen(mgr, player))


def settings_screen(mgr: "Manager", player: Player) -> Screen:
    st = mgr.storage.settings(mgr.platform, player.user_id)
    notify = t("on") if st["friend_notify"] else t("off")
    hour = st["reminder_hour"]
    reminder = t("hour", hour=hour) if hour is not None else t("off")
    return Screen(t("settings", notify=notify, reminder=reminder), [
        [Button(t("btn_friend_notify", state=notify), data("set", "fn"))],
        [Button(t("btn_reminder", state=reminder), data("set", "rm"))],
        [Button(t("btn_menu"), "menu")],
    ])


def reminder_screen(mgr: "Manager", player: Player) -> Screen:
    current = mgr.storage.settings(mgr.platform, player.user_id)["reminder_hour"]

    def mark(text: str, selected: bool) -> str:
        return f"✅ {text}" if selected else text
    choices = [Button(mark(t("btn_reminder_off"), current is None), data("set", "rm", "off"))]
    choices += [Button(mark(t("hour", hour=h), current == h), data("set", "rm", h)) for h in REMINDER_HOURS]
    return Screen(t("reminder_choose"), [choices, [Button(t("btn_back_settings"), "set"),
                                                   Button(t("btn_menu"), "menu")]])


# --- сообщения от бота ---

def friends_notice(names: List[str]) -> Screen:
    names = [html.escape(n, quote=False) for n in names]
    text = ", ".join(names[:MAX_NAMES])
    if len(names) > MAX_NAMES:
        text = t("notify_friends_more", names=text, more=len(names) - MAX_NAMES)
    return Screen(t("notify_friends", names=f"<b>{text}</b>"), [
        [Button(t("btn_train"), "menu")],
        [Button(t("btn_friends"), "fr")],
    ])


def reminder_notice() -> Screen:
    rows = [[Button(TITLES[g], data("new", g))] for g in TRAINING_GAMES]
    return Screen(t("notify_reminder"), rows + [[Button(t("btn_menu"), "menu")]])


class Notifier:
    def __init__(self, mgr: "Manager"):
        self.mgr = mgr

    async def loop(self) -> None:
        """Раз в минуту, в начале минуты: 12:00 наступает ровно в 12:00:00."""
        while True:
            now = self.mgr.clock()
            await self.mgr.sleep(TICK_SECONDS - now % TICK_SECONDS)
            await self.tick()

    def wake(self) -> None:
        """Записана партия: друзьям игрока, возможно, пора уведомление."""
        self.mgr._spawn(self.tick())

    async def tick(self) -> None:
        try:
            due = self.collect()
        except Exception:
            logger.exception("notify: collect failed")
            return
        for uid, screen in due:
            await self.mgr.send_to(uid, screen)

    def collect(self) -> List[Tuple[int, Screen]]:
        """Кому что послать прямо сейчас; день отмечается тут же, до первого await."""
        mgr, storage, platform = self.mgr, self.mgr.storage, self.mgr.platform
        now = mgr.clock()
        since, today, hour = days.day_start(now), days.day_key(now), days.hour(now)
        out: List[Tuple[int, Screen]] = []
        if FRIEND_FROM <= hour < FRIEND_UNTIL:
            for uid, friend_ids in storage.friend_notify_due(platform, since, today).items():
                if mgr.busy(uid):
                    continue
                storage.update_settings(platform, uid, friend_notified_day=today)
                names = storage.names(platform, friend_ids)
                out.append((uid, friends_notice([names.get(f, "?") for f in friend_ids])))
        for uid in storage.reminders_due(platform, hour, since, today):
            if mgr.busy(uid):
                continue
            storage.update_settings(platform, uid, reminded_day=today)
            out.append((uid, reminder_notice()))
        if out:
            logger.info("notify: %s", ", ".join(f"{uid}:{screen.text[:20]!r}" for uid, screen in out))
        return out


def debug_preview(mgr: "Manager", player: Player) -> None:
    """/dbg notify: оба сообщения себе прямо сейчас, без условий."""
    names = mgr.storage.names(mgr.platform, mgr.storage.friends(mgr.platform, player.user_id))
    mgr.send_later(player.user_id, friends_notice(list(names.values()) or ["Друг"]))
    mgr.send_later(player.user_id, reminder_notice())

"""Маршрутизация нажатий, меню, рекорды и таймеры партий.

Транспорт вызывает handle(player, payload, respond):
  respond(reply) отправляет/редактирует сообщение и возвращает его id;
  push(msg_ref, screen) — правка сообщения по таймеру (скрыть фигуры, конец минуты).
Все действия одного пользователя идут под его asyncio.Lock — включая ответ
транспорта, — поэтому сообщение не может «откатиться» к устаревшему экрану.
"""
import asyncio
import html
import logging
import random
import secrets
import time
from collections import defaultdict
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional, Set

from . import debug
from .sessions import GAMES, PREVIEW, INPUT, Player, Session
from .storage import Storage
from .texts import TITLES, t
from .ui import Button, Reply, Screen, data

logger = logging.getLogger(__name__)

PREVIEW_SECONDS = 1.0
ROUND_SECONDS = 60
IDLE_SECONDS = 30 * 60
RECORD_GAMES = ("memo", "matrix", "tower", "sea_full", "sea_reduced")

Respond = Callable[[Reply], Awaitable[Any]]
Push = Callable[[Any, Screen], Awaitable[None]]


def text_payload(text: Optional[str]) -> str:
    """Текстовое сообщение → payload: любое открывает меню, «/dbg …» — отладочная команда."""
    words = (text or "").split()
    if words and words[0].lower() == "/dbg":
        return data("dbg", *words[1:])
    return "menu"


class Manager:
    def __init__(self, storage: Storage, platform: str, push: Push, *,
                 clock: Callable[[], float] = time.time,
                 rng: Optional[random.Random] = None,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 preview_seconds: float = PREVIEW_SECONDS,
                 round_seconds: int = ROUND_SECONDS,
                 debug_users: Iterable[int] = ()):
        self.storage = storage
        self.platform = platform
        self.push = push
        self.clock = clock
        self.rng = rng or random.Random()
        self.sleep = sleep
        self.preview_seconds = preview_seconds
        self.round_seconds = round_seconds
        self.debug_users = frozenset(debug_users)
        self.round_overrides: Dict[int, int] = {}   # /dbg round: длина партии для одного игрока
        self.sessions: Dict[int, Session] = {}
        self.locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._tasks: Set[asyncio.Task] = set()

    # --- вход ---

    async def handle(self, player: Player, payload: str, respond: Respond) -> None:
        uid = player.user_id
        async with self.locks[uid]:
            self._drop_idle()
            reply, shown = self._dispatch(player, payload or "menu")
            ref = await respond(reply)
            if shown is not None and ref is not None:
                shown.msg_ref = ref
            if shown is not None and not shown.finished:
                self._schedule(uid, shown)

    # --- маршрутизация ---

    def _dispatch(self, player: Player, payload: str):
        parts = payload.split(":")
        action = parts[0]
        uid = player.user_id

        if action in ("t", "q"):
            s = self.sessions.get(uid)
            if s is None or len(parts) < 2 or s.sid != parts[1] or s.finished:
                return Reply(note=t("note_stale")), None
            s.last_activity = self.clock()
            if action == "q" or self._time_is_up(s):
                return Reply(s.finish()), s
            try:
                r, c = int(parts[2]), int(parts[3])
            except (IndexError, ValueError):
                return Reply(), None
            if s.timed and s.phase == PREVIEW:
                return Reply(note=t("note_preview")), None
            note = s.tap(r, c)
            if s.over:
                return Reply(s.finish(), note), s
            return Reply(s.screen(), note), s

        # любое действие вне партии прерывает текущую
        if action == "new" and len(parts) > 1 and parts[1] in GAMES:
            s = self.start_session(player, parts[1])
            return Reply(s.screen()), s
        if action == "noop":
            return Reply(), None
        self._abandon(uid)
        if action == "dbg":
            if uid not in self.debug_users:
                return Reply(Screen(t("dbg_off", user_id=uid), [[Button(t("btn_menu"), "menu")]])), None
            return debug.dispatch(self, player, parts[1:])
        if action == "sea":
            return Reply(self.sea_screen()), None
        if action == "rec":
            game = parts[1] if len(parts) > 1 else None
            if game in RECORD_GAMES:
                return Reply(self.records_screen(player, game)), None
            return Reply(self.records_menu()), None
        return Reply(self.menu_screen()), None

    def start_session(self, player: Player, game: str) -> Session:
        self._abandon(player.user_id)
        s = GAMES[game](secrets.token_hex(3), player, self.storage, self.rng, self.clock)
        self.sessions[player.user_id] = s
        return s

    def _time_is_up(self, s: Session) -> bool:
        return s.timed and s.deadline is not None and self.clock() >= s.deadline

    def _abandon(self, uid: int) -> None:
        s = self.sessions.pop(uid, None)
        if s is not None and not s.finished:
            s.finish()

    def _drop_idle(self) -> None:
        now = self.clock()
        for uid, s in list(self.sessions.items()):
            if s.finished or (not s.timed and now - s.last_activity > IDLE_SECONDS):
                del self.sessions[uid]

    # --- таймеры ---

    def _schedule(self, uid: int, s: Session) -> None:
        if not s.timed or not s.preview_pending:
            return
        s.preview_pending = False
        self._spawn(self._hide_later(uid, s, s.round_id))
        if s.deadline is None:
            s.deadline = self.clock() + self.round_overrides.get(uid, self.round_seconds)
            self._spawn(self._finish_later(uid, s))

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    async def _hide_later(self, uid: int, s: Session, round_id: int) -> None:
        await self.sleep(self.preview_seconds)
        async with self.locks[uid]:
            if (self.sessions.get(uid) is not s or s.finished
                    or s.round_id != round_id or s.phase != PREVIEW):
                return
            s.phase = INPUT
            await self._push(s, s.screen())

    async def _finish_later(self, uid: int, s: Session) -> None:
        await self.sleep(max(0.0, s.deadline - self.clock()))
        async with self.locks[uid]:
            if self.sessions.get(uid) is not s or s.finished:
                return
            await self._push(s, s.finish())

    async def _push(self, s: Session, screen: Screen) -> None:
        if s.msg_ref is None:
            return
        try:
            await self.push(s.msg_ref, screen)
        except Exception:
            logger.exception("push failed for user %s", s.player.user_id)

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    # --- экраны вне партии ---

    def menu_screen(self) -> Screen:
        return Screen(t("menu"), [
            [Button(TITLES["memo"], data("new", "memo"))],
            [Button(TITLES["matrix"], data("new", "matrix"))],
            [Button(TITLES["tower"], data("new", "tower"))],
            [Button(t("btn_sea"), "sea")],
            [Button(t("btn_records"), "rec")],
        ])

    def sea_screen(self) -> Screen:
        return Screen(t("sea_choose"), [
            [Button(t("btn_sea_full"), data("new", "sea_full"))],
            [Button(t("btn_sea_reduced"), data("new", "sea_reduced"))],
            [Button(t("btn_menu"), "menu")],
        ])

    def records_menu(self) -> Screen:
        rows = [[Button(TITLES[g], data("rec", g))] for g in RECORD_GAMES]
        return Screen(t("records_choose"), rows + [[Button(t("btn_menu"), "menu")]])

    def records_screen(self, player: Player, game: str) -> Screen:
        top = self.storage.top(self.platform, game)
        lines = [f"🏆 <b>{TITLES[game]}</b>", ""]
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        for i, (user_id, name, score) in enumerate(top, 1):
            mark = " ← вы" if user_id == player.user_id else ""
            lines.append(f"{medals.get(i, f'{i}.')} {html.escape(name, quote=False)} — <b>{score}</b>{mark}")
        if not top:
            lines.append(t("records_empty"))
        best = self.storage.load_progress(self.platform, player.user_id, game).best_score
        if best:
            lines += ["", t("records_mine", score=best)]
        return Screen("\n".join(lines), [
            [Button(t("btn_play"), data("new", game))],
            [Button(t("btn_records"), "rec"), Button(t("btn_menu"), "menu")],
        ])

"""Маршрутизация нажатий, меню, рекорды и таймеры партий.

Транспорт вызывает handle(player, payload, respond):
  respond(reply) отправляет/редактирует сообщение и возвращает его id;
  push(msg_ref, screen) — правка сообщения по таймеру: отсчёт «3, 2, 1», показ,
  ввод, ход таймера партии, конец минуты.
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

from . import days, debug, friends, heroes, journey_art, locations, motivation, notify, progress
from . import seafight_mp as mp
from .multiplayer import ACTIONS as MP_ACTIONS, Multiplayer, looks_like_code
from .seafight_mp import game_type as mp_game_type
from .sessions import COUNTDOWN_FROM, DONE, GAMES, INPUT, PREVIEW, REVIEW, MemoSession, Player, Session, TimedSession
from .storage import Storage
from .texts import TITLES, days_word, t, wins_word
from .ui import Button, Reply, Screen, data

logger = logging.getLogger(__name__)

PREVIEW_SECONDS = 1.0
COUNTDOWN_SECONDS = 2.0   # «3, 2, 1» перед каждым показом
TIMER_TICK_SECONDS = 5.0  # как часто обновлять таймер партии, если игрок не нажимает
MEMO_CLOSE_SECONDS = 3.0  # несовпавшая пара в мемо закрывается сама (или раньше — нажатием)
REVIEW_SECONDS = 2.0      # разбор ошибки (найденные клетки и ошибочная) и итог пройденного раунда
ROUND_SECONDS = 60
IDLE_SECONDS = 30 * 60
MP_BLINK_SECONDS = 0.4    # мигание потопленного корабля в бою с другом
AI_THINK_SECONDS = 1.0    # пауза перед ходом компьютера
RECORD_GAMES = ("memo", "matrix", "tower", "path", "ai_normal", "ai_advanced", "mp_full", "mp_reduced")
RATING_GAMES = ("mp_full", "mp_reduced")   # бой с другом: таблица — рейтинг Elo, а не рекорды
AI_GAMES = {"ai_normal": "normal", "ai_advanced": "advanced"}   # бой с компьютером: таблица побед

Respond = Callable[[Reply], Awaitable[Any]]
Push = Callable[[Any, Screen], Awaitable[None]]
Send = Callable[[int, Screen], Awaitable[Any]]    # новое сообщение в чат (chat_id) → его id


def start_payload(param: Optional[str]) -> str:
    """Параметр ссылки ?start=… → payload: mp_<код> — бой с другом, fr_<код> — подружиться."""
    if param and param.startswith("mp_"):
        return data("mpj", param[3:].upper())
    if param and param.startswith("fr_"):
        return data("frj", param[3:].upper())
    return "menu"


def text_payload(text: Optional[str]) -> str:
    """Текстовое сообщение → payload: любое открывает меню, «/dbg …» — отладочная команда,
    «/start mp_КОД» или сам код приглашения — подключиться к бою с другом,
    «/start fr_КОД» или код друга — подружиться."""
    words = (text or "").split()
    if words and words[0].lower() == "/dbg":
        return data("dbg", *words[1:])
    if len(words) == 2 and words[0].lower() == "/start":
        return start_payload(words[1])
    if len(words) == 1 and looks_like_code(words[0]):
        return data("mpj", words[0].upper())
    if len(words) == 1 and friends.looks_like_code(words[0]):
        return data("frj", words[0].upper())
    return "menu"


class Manager:
    def __init__(self, storage: Storage, platform: str, push: Push, *,
                 clock: Callable[[], float] = time.time,
                 rng: Optional[random.Random] = None,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
                 preview_seconds: float = PREVIEW_SECONDS,
                 countdown_seconds: float = COUNTDOWN_SECONDS,
                 tick_seconds: float = TIMER_TICK_SECONDS,
                 memo_close_seconds: float = MEMO_CLOSE_SECONDS,
                 review_seconds: float = REVIEW_SECONDS,
                 round_seconds: int = ROUND_SECONDS,
                 debug_users: Iterable[int] = (),
                 send: Optional[Send] = None,
                 start_link: Callable[[str], str] = lambda param: param,
                 mp_blink_seconds: float = MP_BLINK_SECONDS,
                 ai_think_seconds: float = AI_THINK_SECONDS,
                 run_cpu: Optional[Callable[..., Awaitable[Any]]] = None,
                 live_ref: Callable[[Any], bool] = lambda ref: False):
        self.storage = storage
        self.platform = platform
        self.push = push
        self.send = send
        self.start_link = start_link          # ссылка на бота с ?start=<param>: бой с другом, приглашение в друзья
        self.mp_blink_seconds = mp_blink_seconds
        self.ai_think_seconds = ai_think_seconds
        # тяжёлый расчёт (ход компьютера) — в потоке, чтобы бот не замирал; тесты считают на месте
        self.run_cpu = run_cpu or asyncio.to_thread
        # место показа, которое игрок видит постоянно (экран Mini App): событию партии там не нужно
        # новое сообщение-уведомление — экран обновляется на месте
        self.live_ref = live_ref
        self.clock = clock
        self.rng = rng or random.Random()
        self.sleep = sleep
        self.preview_seconds = preview_seconds
        self.countdown_seconds = countdown_seconds
        self.tick_seconds = tick_seconds
        self.memo_close_seconds = memo_close_seconds
        self.review_seconds = review_seconds
        self.round_seconds = round_seconds
        self.debug_users = frozenset(debug_users)
        self.round_overrides: Dict[int, int] = {}   # /dbg round: длина партии для одного игрока
        self.sessions: Dict[int, Session] = {}
        self.locks: Dict[int, asyncio.Lock] = defaultdict(asyncio.Lock)
        self._tasks: Set[asyncio.Task] = set()
        self.mp = Multiplayer(self)
        self.notifier = notify.Notifier(self)
        self._background: Optional[asyncio.Task] = None

    # --- вход ---

    async def handle(self, player: Player, payload: str, respond: Respond) -> None:
        uid = player.user_id
        async with self.locks[uid]:
            self._drop_idle()
            parts = (payload or "menu").split(":")
            if parts[0] in MP_ACTIONS:
                # бой с другом: отвечает и правит сообщения соперника сам, под замком партии
                self._abandon(uid)
                await self.mp.handle(player, parts, respond)
                return
            reply, shown = self._dispatch(player, payload or "menu")
            async with self.mp.guard(uid):
                ref = await respond(reply)
                if ref is not None:
                    self.mp.detach(uid, ref)    # сообщение партии с другом ушло на другой экран
            if shown is not None and ref is not None:
                shown.msg_ref = ref
                shown.rendered_at = self.clock()
            if shown is not None and not shown.finished:
                self._schedule(uid, shown)

    # --- маршрутизация ---

    def _dispatch(self, player: Player, payload: str):
        parts = payload.split(":")
        action = parts[0]
        uid = player.user_id

        if action in ("t", "q", "b"):
            s = self.sessions.get(uid)
            if s is None or len(parts) < 2 or s.sid != parts[1] or s.finished:
                return Reply(note=t("note_stale")), None
            s.last_activity = self.clock()
            if action == "q":
                return Reply(s.finish()), s
            if s.in_done():
                # итог раунда или собранного поля: любое нажатие — дальше
                return Reply(s.skip_done()), s
            if action == "b":
                # чёрная клетка вне поля
                return Reply(), None
            try:
                r, c = int(parts[2]), int(parts[3])
            except (IndexError, ValueError):
                return Reply(), None
            if s.timed and s.phase != INPUT:
                # отсчёт или показ: нажатие не засчитывается
                return Reply(note=s.tap(r, c)), None
            note = s.tap(r, c)
            if s.over:
                return Reply(s.finish(), note), s
            return Reply(s.screen(), note), s

        # любое действие вне партии прерывает текущую
        if action == "new" and len(parts) > 1 and parts[1] in GAMES:
            s = self.start_session(player, parts[1])
            return Reply(s.screen()), s
        if action == "new" and len(parts) > 1 and parts[1].startswith("sea_"):
            # «найди корабли» заменена боем с компьютером: старые кнопки ведут в морской бой
            self._abandon(uid)
            return Reply(self.sea_screen(player)), None
        if action == "noop":
            return Reply(), None
        self._abandon(uid)
        # имя и чат нужны друзьям и сообщениям от бота, даже если игрок ещё ни разу не доиграл партию
        self.storage.upsert_user(player.platform, uid, player.name, player.chat_id, self.clock())
        if action in friends.ACTIONS:
            return friends.dispatch(self, player, parts), None
        if action in notify.ACTIONS:
            return notify.dispatch(self, player, parts), None
        if action in progress.ACTIONS:
            return Reply(progress.dispatch(self, player, parts)), None
        if action in heroes.ACTIONS:
            return heroes.dispatch(self, player, parts), None
        if action == "dbg":
            if uid not in self.debug_users:
                return Reply(Screen(t("dbg_off", user_id=uid), [[Button(t("btn_menu"), "menu")]])), None
            return debug.dispatch(self, player, parts[1:])
        if action == "sea":
            return Reply(self.sea_screen(player)), None
        if action == "jr":
            zone = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else None
            return Reply(self.journey_screen(player, zone)), None
        if action == "rec":
            game = parts[1] if len(parts) > 1 else None
            if game in RECORD_GAMES:
                return Reply(self.records_screen(player, game)), None
            return Reply(self.records_menu()), None
        return Reply(self.menu_screen(player)), None

    def start_session(self, player: Player, game: str) -> Session:
        self._abandon(player.user_id)
        s = GAMES[game](secrets.token_hex(3), player, self.storage, self.rng, self.clock)
        s.on_saved = lambda: self.partia_saved(s.player.user_id, s.motivation_events, s.journey_after)
        if isinstance(s, TimedSession) and s.clock_limited:
            s.round_seconds = self.round_overrides.get(player.user_id, self.round_seconds)
        self.sessions[player.user_id] = s
        return s

    def partia_saved(self, uid: int, e: Optional[motivation.Events], j: Optional[motivation.Journey]) -> None:
        """Партия записана: уведомления друзьям; новая зона и открытка за серию — отдельными сообщениями."""
        self.notifier.wake()
        if e is None or j is None:
            return
        if e.reward:
            self.send_later(uid, Screen(
                t("streak_card", n=j.streak, word=days_word(j.streak), steps=motivation.STREAK_REWARD_STEPS),
                [[Button(t("btn_journey"), "jr"), Button(t("btn_menu"), "menu")]],
                image=journey_art.render_card(j.streak)))
        if e.zones_opened:
            zone = e.zones_opened[-1]
            _, step, size = motivation.zone_of(j.steps)
            self.send_later(uid, Screen(
                self.reveal_text(zone, size),
                [[Button(t("btn_journey"), "jr"), Button(t("btn_menu"), "menu")]],
                image=journey_art.render_zone(zone, step, size, "reveal", heroes.current(self, uid))))

    @staticmethod
    def reveal_text(zone: int, size: int) -> str:
        """Новая локация: чем кончилась прошлая и что ждёт в этой."""
        loc, prev = locations.of_zone(zone), locations.of_zone(zone - 1)
        if loc is None or prev is None:
            return t("journey_reveal", zone=motivation.zone_title(zone), size=size)
        return t("journey_reveal_story", finish=prev.finish, zone=loc.title, intro=loc.intro, size=size,
                 chest=motivation.CHEST_COINS)

    def _abandon(self, uid: int) -> None:
        s = self.sessions.pop(uid, None)
        if s is not None and not s.finished:
            s.finish()

    def _drop_idle(self) -> None:
        now = self.clock()
        for uid, s in list(self.sessions.items()):
            # матрица, пока время не вышло, кончится сама; остальные партии убираем после простоя
            on_clock = isinstance(s, TimedSession) and s.clock_limited
            if s.finished:
                del self.sessions[uid]
            elif now - s.last_activity > IDLE_SECONDS and not (on_clock and s.seconds_left() > 0):
                if on_clock:
                    s.finish()      # время вышло, а последний раунд так и не доигран: очки партии записываем
                del self.sessions[uid]

    # --- таймеры ---

    def _schedule(self, uid: int, s: Session) -> None:
        if isinstance(s, MemoSession) and s.close_pending:
            s.close_pending = False
            self._spawn(self._close_mismatch_later(uid, s, s.mismatch_id))
        if isinstance(s, MemoSession) and s.done_pending:
            s.done_pending = False
            self._spawn(self._finish_later(uid, s))
        if isinstance(s, TimedSession) and s.review_pending:
            s.review_pending = False
            self._spawn(self._review_then_next(uid, s, s.round_id))
        if isinstance(s, TimedSession) and s.round_pending:
            s.round_pending = False
            self._spawn(self._run_round(uid, s, s.round_id))

    def _spawn(self, coro) -> asyncio.Task:
        task = asyncio.create_task(coro)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
        return task

    def _alive(self, uid: int, s: TimedSession, round_id: int) -> bool:
        return self.sessions.get(uid) is s and not s.finished and s.round_id == round_id

    async def _step(self, uid: int, s: TimedSession, round_id: int, change: Callable[[], None]) -> bool:
        """Под замком: если раунд ещё тот же — применить change и показать экран."""
        async with self.locks[uid]:
            if not self._alive(uid, s, round_id):
                return False
            change()
            await self._push(s, s.screen())
            return True

    async def _close_mismatch_later(self, uid: int, s: MemoSession, mismatch_id: int) -> None:
        """Закрыть несовпавшую пару, если игрок не закрыл её нажатием раньше."""
        await self.sleep(self.memo_close_seconds)
        async with self.locks[uid]:
            if (self.sessions.get(uid) is not s or s.finished
                    or s.mismatch_id != mismatch_id or not s.board.close_mismatch()):
                return
            await self._push(s, s.screen())

    async def _finish_later(self, uid: int, s: MemoSession) -> None:
        """Собранное поле мемо видно review_seconds, затем результат (если игрок не нажал раньше)."""
        await self.sleep(self.review_seconds)
        async with self.locks[uid]:
            if self.sessions.get(uid) is s and not s.finished:
                await self._push(s, s.finish())

    async def _review_then_next(self, uid: int, s: TimedSession, round_id: int) -> None:
        """Разбор ошибки или итог раунда review_seconds, затем новый раунд с отсчётом
        (или конец партии: раунды кончились или вышло время)."""
        await self.sleep(self.review_seconds)
        async with self.locks[uid]:
            if not self._alive(uid, s, round_id) or s.phase not in (REVIEW, DONE):
                return
            await self._push(s, s.advance())
            if not s.finished:
                self._schedule(uid, s)

    async def _run_round(self, uid: int, s: TimedSession, round_id: int) -> None:
        """Отсчёт «3, 2, 1» → показ → ввод с ходом таймера до конца раунда или партии."""
        step = self.countdown_seconds / COUNTDOWN_FROM
        for n in range(COUNTDOWN_FROM - 1, 0, -1):
            await self.sleep(step)
            if not await self._step(uid, s, round_id, lambda n=n: setattr(s, "countdown", n)):
                return
        await self.sleep(step)
        if not await self._step(uid, s, round_id, lambda: setattr(s, "phase", PREVIEW)):
            return
        await self.sleep(self.preview_seconds)
        if not await self._step(uid, s, round_id, s.begin_input):
            return
        if not s.clock_limited:
            return

        while True:
            await self.sleep(min(self.tick_seconds, s.seconds_left()))
            async with self.locks[uid]:
                if not self._alive(uid, s, round_id) or s.phase != INPUT:
                    return
                if s.time_is_up():
                    # время вышло: раунд доигрывается, партию закончит итог или разбор
                    await self._push(s, s.screen())
                    return
                # нажатие только что обновило экран — таймер на нём свежий
                if self.clock() - s.rendered_at >= 1.0:
                    await self._push(s, s.screen())

    async def _push(self, s: Session, screen: Screen) -> None:
        if s.msg_ref is None:
            return
        s.rendered_at = self.clock()
        try:
            await self.push(s.msg_ref, screen)
        except Exception:
            logger.exception("push failed for user %s", s.player.user_id)

    def restore(self) -> int:
        """После перезапуска бота: незаконченные бои с другом и их таймеры."""
        return self.mp.restore()

    def start_background(self) -> None:
        """Уведомления от друзей и напоминания: цикл раз в минуту. Нужен send."""
        if self.send is not None and self._background is None:
            self._background = self._spawn(self.notifier.loop())

    # --- сообщения от бота ---

    def busy(self, uid: int) -> bool:
        """Игрок посреди партии: сообщение от бота сейчас помешает."""
        s = self.sessions.get(uid)
        if s is not None and not s.finished:
            return True
        game = self.mp.open_game(uid)
        if game is None or game.status == mp.WAITING:
            return False
        # брошенный бой с компьютером (без лимита времени он ждёт вечно) уведомлениям не мешает
        return not (game.vs_ai and self.clock() - game.turn_started_at > IDLE_SECONDS)

    async def send_to(self, uid: int, screen: Screen) -> Any:
        """Новое сообщение игроку в его чат с ботом (chat_id — из users)."""
        user = self.storage.user(self.platform, uid)
        if self.send is None or user is None or user["chat_id"] is None:
            return None
        try:
            return await self.send(user["chat_id"], screen)
        except Exception:
            logger.exception("send failed for user %s", uid)
            return None

    def send_later(self, uid: int, screen: Screen) -> None:
        self._spawn(self.send_to(uid, screen))

    async def shutdown(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await asyncio.gather(*self._tasks, return_exceptions=True)

    # --- экраны вне партии ---

    def menu_screen(self, player: Player) -> Screen:
        uid = player.user_id
        journey = motivation.journey(self.storage, self.platform, uid)
        lines = "\n".join(motivation.menu_lines(journey, days.day_key(self.clock()),
                                                 heroes.balance(self, uid, journey)))
        zone, step, size = motivation.zone_of(journey.steps)
        image = journey_art.render_zone(zone, step, size, hero=heroes.current(self, uid))
        return Screen(t("menu_with", progress=lines), image=image, rows=[
            [progress.daily_button(self, player.user_id, journey)],
            [Button(TITLES["memo"], data("new", "memo"))],
            [Button(TITLES["matrix"], data("new", "matrix"))],
            [Button(TITLES["tower"], data("new", "tower"))],
            [Button(TITLES["path"], data("new", "path"))],
            [Button(t("btn_sea"), "sea")],
            [Button(t("btn_journey"), "jr"), Button(t("btn_progress"), "prog")],
            [Button(t("btn_records"), "rec")],
            [Button(t("btn_friends"), "fr"), Button(t("btn_invite_friend"), "fri")],
            [Button(t("btn_settings"), "set")],
        ])

    def journey_screen(self, player: Player, zone: Optional[int] = None) -> Screen:
        """«Мой путь»: текущая зона или пройденная (листается ◀️ ▶️), как альбом."""
        uid = player.user_id
        journey = motivation.journey(self.storage, self.platform, uid)
        current, step, size = motivation.zone_of(journey.steps)
        zone = current if zone is None else max(0, min(zone, current))
        title, hero, loc = motivation.zone_title(zone), heroes.current(self, uid), locations.of_zone(zone)
        if zone == current:
            line = t("journey_zone_now", zone=title, step=step, size=size)
            image = journey_art.render_zone(zone, step, size, hero=hero)
        else:
            line = (t("journey_zone_done_story", zone=title, finish=loc.finish) if loc
                    else t("journey_zone_done", zone=title))
            done = motivation.zone_size(zone)
            image = journey_art.render_zone(zone, done, done, "done", hero)
        best = journey.best_streak
        head = [t("journey_title", n=zone + 1, total=current + 1)]
        if loc is not None:
            head.append(t("journey_chapter", n=loc.chapter, title=loc.chapter_title))
        text = "\n".join(head + [
            "", line, "",
            t("journey_totals", steps=journey.steps, best=best, word=days_word(best)), "",
            t("journey_rules", cap=motivation.DAY_STEP_CAP),
        ])
        nav = []
        if zone > 0:
            nav.append(Button(t("btn_prev"), data("jr", zone - 1)))
        if zone < current:
            nav.append(Button(t("btn_next"), data("jr", zone + 1)))
        rows = ([nav] if nav else []) + [[Button(t("btn_heroes"), "hr"), Button(t("btn_menu"), "menu")]]
        return Screen(text, rows, image=image)

    def sea_screen(self, player: Player) -> Screen:
        if self.mp.open_game(player.user_id):
            rows = [[Button(t("btn_mp_return"), "mpb")]]
        else:
            rows = [[Button(t("btn_ai"), "ai")], [Button(t("btn_mp"), "mp")]]
        return Screen(t("sea_choose"), rows + [[Button(t("btn_menu"), "menu")]])

    def records_menu(self) -> Screen:
        rows = [[Button(TITLES[g], data("rec", g))] for g in RECORD_GAMES]
        return Screen(t("records_choose"), rows + [[Button(t("btn_menu"), "menu")]])

    def records_screen(self, player: Player, game: str) -> Screen:
        if game in RATING_GAMES:
            return self.rating_screen(player, game)
        if game in AI_GAMES:
            return self.ai_records_screen(player, game)
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

    def ai_records_screen(self, player: Player, game: str) -> Screen:
        level = AI_GAMES[game]
        top = self.storage.top_ai(self.platform, level)
        lines = [t("records_ai", title=TITLES[game]), ""]
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        for i, (user_id, name, won, lost) in enumerate(top, 1):
            lines.append(t("records_ai_line", place=medals.get(i, f"{i}."), name=html.escape(name, quote=False),
                           won=won, word=wins_word(won), total=won + lost,
                           me=" ← вы" if user_id == player.user_id else ""))
        if not top:
            lines.append(t("records_empty"))
        mine = self.storage.ai_results_of(self.platform, player.user_id).get(level)
        if mine:
            lines += ["", t("records_ai_mine", won=mine[0], total=sum(mine))]
        return Screen("\n".join(lines), [
            [Button(t("btn_ai"), data("ain", level))],
            [Button(t("btn_records"), "rec"), Button(t("btn_menu"), "menu")],
        ])

    def rating_screen(self, player: Player, game: str) -> Screen:
        top = self.storage.top_ratings(self.platform, mp_game_type(game[len("mp_"):]))
        lines = [t("records_rating", title=TITLES[game]), ""]
        medals = {1: "🥇", 2: "🥈", 3: "🥉"}
        for i, (user_id, name, rating, won, lost) in enumerate(top, 1):
            mark = " ← вы" if user_id == player.user_id else ""
            lines.append(f"{medals.get(i, f'{i}.')} {html.escape(name, quote=False)} — <b>{rating}</b>"
                         f" ({won}/{lost}){mark}")
        if not top:
            lines.append(t("records_empty"))
        return Screen("\n".join(lines), [
            [Button(t("btn_mp"), "mp")],
            [Button(t("btn_records"), "rec"), Button(t("btn_menu"), "menu")],
        ])

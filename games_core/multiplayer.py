"""Морской бой с другом: нажатия, экраны и таймеры. Правила — seafight_mp.

Manager отдаёт сюда payload'ы mp…, а Multiplayer сам отвечает игроку (respond)
и правит сообщение соперника (push) или присылает ему новое (send). Все изменения
партии и все правки её сообщений идут под замком партии — экран у игрока не может
«откатиться» к устаревшему. Партия сохраняется в SQLite после каждого изменения
и после перезапуска бота восстанавливается вместе с таймерами (restore).

Payload'ы (сообщение у игрока одно на партию: своё поле — текстом, поле соперника — кнопками):
  mp                       выбор времени на ход
  mpn:<сек>[:<набор>[:<расстановка>]]  шаги выбора; последний создаёт приглашение
  mpj:<код>                подключиться (ссылка ?start=mp_<код> или код сообщением)
  mpx:<код>                отменить приглашение
  mpf:<код>:<r>:<c>        выстрел
  mpp:<код>:<r>:<c>, mpk:<код>, mpz:<код>, mpy:<код>  расстановка: клетка, зафиксировать, сначала, готов
  mpg:<код>                сдаться (до начала боя — отменить партию)
  mpb                      вернуться к своей партии
"""
import asyncio
import contextlib
import html
import logging
from collections import defaultdict
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from . import seafight_mp as mp
from . import seafight_solo as sea
from .sessions import SEA_SYMBOLS, Player
from .texts import t
from .ui import Button, Reply, Screen, data

if TYPE_CHECKING:
    from .manager import Manager

logger = logging.getLogger(__name__)

ACTIONS = ("mp", "mpn", "mpj", "mpx", "mpf", "mpp", "mpk", "mpz", "mpy", "mpg", "mpb")

OWN_SHIP = "🔳"
PLACE_CURRENT = "🔲"
PLACE_FORBIDDEN = "🟩"
BLINKS = 3                 # мигание потопленного корабля: 3 раза 💢 ↔ 💥
PLACEMENT_TICK = 30        # как часто обновлять таймер расстановки


def start_payload(payload: Optional[str]) -> str:
    """Параметр ссылки ?start=… → payload: mp_<код> — подключиться к партии."""
    if payload and payload.startswith("mp_"):
        return data("mpj", payload[3:].upper())
    return "menu"


def looks_like_code(word: str) -> bool:
    w = word.upper()
    return len(w) == mp.CODE_LEN and all(ch in mp.CODE_ALPHABET for ch in w) and any(ch.isdigit() for ch in w)


def fmt_left(seconds: float) -> str:
    s = int(seconds + 0.999)       # 9.2 с → «0:10»: столько ещё есть на ход
    return f"{s // 60}:{s % 60:02d}" if s < 3600 else f"{s // 3600}:{s % 3600 // 60:02d}:{s % 60:02d}"


def turn_tick(limit: int) -> int:
    """Как часто перерисовывать таймер хода: при часе на ход — раз в минуту, как в TG."""
    return max(5, min(60, limit // 6))


def menu_row() -> List[Button]:
    return [Button(t("btn_menu"), "menu")]


class Multiplayer:
    def __init__(self, mgr: "Manager"):
        self.mgr = mgr
        self.games: Dict[str, mp.MpGame] = {}       # открытые партии и закончившиеся, пока мигает корабль
        self.locks: Dict[str, asyncio.Lock] = defaultdict(asyncio.Lock)
        self.animating: set = set()                 # коды партий, где мигает последний корабль
        self.blinking: Dict[str, int] = defaultdict(int)   # сколько анимаций идёт в партии
        self.turn_tasks: Dict[str, asyncio.Task] = {}
        self.placement_tasks: Dict[Tuple[str, int], asyncio.Task] = {}

    # --- вход ---

    def open_game(self, user_id: int) -> Optional[mp.MpGame]:
        return next((g for g in self.games.values()
                     if g.status in mp.OPEN and g.side(user_id) is not None), None)

    @contextlib.asynccontextmanager
    async def guard(self, user_id: int):
        """Замки партий игрока: под ними транспорт правит сообщение, которое может оказаться
        сообщением партии, — чтобы правка не разминулась с ходом соперника. Порядок замков
        постоянный (по коду), поэтому два guard не заблокируют друг друга."""
        codes = sorted(g.code for g in self.games.values() if g.side(user_id) is not None)
        async with contextlib.AsyncExitStack() as stack:
            for code in codes:
                await stack.enter_async_context(self.locks[code])
            yield

    def detach(self, user_id: int, ref) -> None:
        """Игрок увёл сообщение партии на другой экран (меню, другая игра): больше его не правим.
        Вернуть — «Вернуться к партии». Вызывать под guard()."""
        for game in self.games.values():
            side = game.side(user_id)
            if side is not None and side.msg_ref == ref:
                side.msg_ref = None
                self._save(game)

    async def handle(self, player: Player, parts: List[str], respond) -> None:
        action, args = parts[0], parts[1:]

        async def respond_here(reply: Reply):
            ref = await respond(reply)
            if ref is not None:
                self.detach(player.user_id, ref)
            return ref

        if action in ("mp", "mpn", "mpj"):
            async with self.guard(player.user_id):
                await self._entry(player, action, args, respond_here)
            return
        if action == "mpb":
            game = self.open_game(player.user_id)
            if game is None:
                async with self.guard(player.user_id):
                    await respond_here(Reply(self.mgr.sea_screen(player)))
            else:
                async with self.locks[game.code]:
                    await self._show(game, game.side(player.user_id), respond_here)
        elif args:
            code = args[0]
            game = self.games.get(code)
            if game is None or game.side(player.user_id) is None:
                await respond(Reply(note=t("note_mp_over")))
                return
            async with self.locks[code]:
                await self._game_action(player, game, action, args[1:], respond_here)
        else:
            await respond(Reply(note=t("note_stale")))

    async def _entry(self, player: Player, action: str, args: List[str], respond) -> None:
        if action == "mp":
            await respond(Reply(self._busy_screen(player) or self._time_screen()))
        elif action == "mpn":
            await self._wizard(player, args, respond)
        elif args:
            await self._join(player, args[0].upper(), respond)
        else:
            await respond(Reply(self._time_screen()))

    async def _game_action(self, player: Player, game: mp.MpGame, action: str, args: List[str], respond):
        me = game.side(player.user_id)
        if self.games.get(game.code) is not game:          # пока ждали замок, партия закончилась
            await respond(Reply(note=t("note_mp_over")))
            return
        cell = None
        if action in ("mpf", "mpp"):
            try:
                cell = int(args[0]), int(args[1])
            except (IndexError, ValueError):
                await respond(Reply(note=t("note_stale")))
                return
        if action == "mpf":
            await self._fire(game, me, *cell, respond)
        elif action == "mpx":
            await self._cancel_invite(game, me, respond)
        elif action == "mpg":
            await self._surrender(game, me, respond)
        elif action in ("mpp", "mpk", "mpz", "mpy"):
            await self._placement(game, me, action, cell, respond)
        else:
            await respond(Reply(note=t("note_stale")))

    # --- создание и подключение ---

    def _busy_screen(self, player: Player) -> Optional[Screen]:
        if self.open_game(player.user_id) is None:
            return None
        return Screen(t("mp_busy"), [[Button(t("btn_mp_return"), "mpb")], menu_row()])

    def _time_screen(self) -> Screen:
        def b(sec):
            return Button(t(f"mp_time_{sec}"), data("mpn", sec))
        return Screen(f"{t('mp_title')}\n\n{t('mp_choose_time')}", [
            [b(0)], [b(10), b(30)], [b(60), b(300)], [b(3600)],
            [Button(t("btn_cancel"), "sea")],
        ])

    async def _wizard(self, player: Player, args: List[str], respond) -> None:
        try:
            limit = int(args[0])
        except (IndexError, ValueError):
            limit = -1
        ship_set = args[1] if len(args) > 1 else None
        mode = args[2] if len(args) > 2 else None
        if limit not in mp.TIME_LIMITS or (ship_set and ship_set not in sea.SHIP_SETS) \
                or (mode and mode not in (mp.AUTO, mp.MANUAL)):
            await respond(Reply(self._time_screen()))
            return
        busy = self._busy_screen(player)
        if busy:
            await respond(Reply(busy))
            return
        cancel = [Button(t("btn_cancel"), "sea")]
        if ship_set is None:
            await respond(Reply(Screen(f"{t('mp_title')}\n\n{t('mp_choose_set')}", [
                [Button(t("btn_sea_full"), data("mpn", limit, "full"))],
                [Button(t("btn_sea_reduced"), data("mpn", limit, "reduced"))],
                cancel,
            ])))
            return
        if mode is None:
            await respond(Reply(Screen(f"{t('mp_title')}\n\n{t('mp_choose_mode')}", [
                [Button(t("btn_mp_auto"), data("mpn", limit, ship_set, mp.AUTO))],
                [Button(t("btn_mp_manual"), data("mpn", limit, ship_set, mp.MANUAL))],
                cancel,
            ])))
            return
        code = self._new_code()
        now = self.mgr.clock()
        game = mp.MpGame(code, ship_set, mode, limit, self._side(player), created_at=now)
        self.games[code] = game
        async with self.locks[code]:
            self._save(game)
            await self._show(game, game.host, respond)

    def _new_code(self) -> str:
        while True:
            code = mp.new_code(self.mgr.rng)
            if code not in self.games and not self.mgr.storage.mp_code_used(self.mgr.platform, code):
                return code

    def _side(self, player: Player) -> mp.Side:
        return mp.Side(player.user_id, player.name, player.chat_id)

    async def _join(self, player: Player, code: str, respond) -> None:
        game = self.games.get(code)
        uid = player.user_id
        if game is None or game.status not in mp.OPEN:
            await respond(Reply(self._info_screen(t("mp_not_found"))))
            return
        if game.host.user_id == uid:
            await respond(Reply(self._info_screen(t("mp_own_link"), [[Button(t("btn_mp_return"), "mpb")]])))
            return
        if game.status != mp.WAITING:
            await respond(Reply(self._info_screen(t("mp_started_already"))))
            return
        busy = self._busy_screen(player)
        if busy:
            await respond(Reply(busy))
            return
        async with self.locks[code]:
            if game.status != mp.WAITING:
                await respond(Reply(self._info_screen(t("mp_started_already"))))
                return
            now = self.mgr.clock()
            game.join(self._side(player), now, self.mgr.rng)
            self._save(game)
            await self._show(game, game.guest, respond)
            await self._move_to_new_message(game, game.host,
                                            t("mp_joined_host", name=html.escape(player.name, quote=False)))
            self._schedule(game)

    def _info_screen(self, text: str, extra: Optional[List[List[Button]]] = None) -> Screen:
        return Screen(text, (extra or []) + [[Button(t("btn_mp"), "mp")], menu_row()])

    async def _cancel_invite(self, game: mp.MpGame, me: mp.Side, respond) -> None:
        if game.status != mp.WAITING or me is not game.host:
            await respond(Reply(note=t("mp_started_already")))
            return
        game.end(None, mp.END_CANCELLED, self.mgr.clock())
        self._close(game)
        await respond(Reply(self._info_screen(t("mp_invite_cancelled"))))

    # --- расстановка ---

    async def _placement(self, game: mp.MpGame, me: mp.Side, action: str, cell, respond) -> None:
        if game.status != mp.PLACING or me.ready:
            await respond(Reply(note=t("note_stale")))
            return
        p = me.placement
        note = None
        if action == "mpp":
            error = p.tap(*cell)
            note = t(error) if error else None
        elif action == "mpk":
            p.fix()
        elif action == "mpz":
            p.reset()
        elif action == "mpy":
            if not p.is_complete():
                await respond(Reply(note=t("note_stale")))
                return
            started = game.set_ready(me.user_id, self.mgr.clock())
            self._save(game)
            await self._show(game, me, respond)
            if started:
                other = game.opponent(me.user_id)
                await self._move_to_new_message(game, other, t("mp_both_ready"))
                self._schedule(game)
            return
        self._save(game)
        await self._show(game, me, respond, note)

    # --- бой ---

    async def _fire(self, game: mp.MpGame, me: mp.Side, r: int, c: int, respond) -> None:
        if game.status != mp.ACTIVE:
            await respond(Reply(note=t("note_mp_over")))
            return
        if game.turn != me.user_id:
            await respond(Reply(note=t("note_not_your_turn")))
            return
        now = self.mgr.clock()
        result = game.fire(me.user_id, r, c, now)
        if result == sea.IGNORED:
            await respond(Reply(note=t("note_already_shot")))
            return
        other = game.opponent(me.user_id)
        sunk = []
        if result in (sea.SUNK, sea.WON):
            sunk = game.ship_cells_sunk_by(game.moves[-1])
        if result == sea.WON:
            self._settle(game)
            self.animating.add(game.code)
        self._save(game)
        note = {sea.MISS: t("note_miss"), sea.HIT: t("note_hit")}.get(result, t("note_sunk"))
        await self._show(game, me, respond, note)
        await self._push(game, other)
        if sunk:
            self.mgr._spawn(self._animate(game, me.user_id, sunk, len(game.moves)))
        if result != sea.WON:
            self._schedule(game)

    async def _surrender(self, game: mp.MpGame, me: mp.Side, respond) -> None:
        now = self.mgr.clock()
        other = game.opponent(me.user_id)
        if game.status == mp.WAITING:
            await self._cancel_invite(game, me, respond)
            return
        if game.status == mp.PLACING:
            game.end(None, mp.END_CANCELLED, now)
            self._close(game)
            await respond(Reply(self._info_screen(t("mp_cancelled_you"))))
            await self._push_screen(game, other, self._info_screen(t("mp_cancelled_them")))
            return
        if game.status != mp.ACTIVE:
            await respond(Reply(note=t("note_mp_over")))
            return
        game.end(other.user_id, mp.END_SURRENDER, now)
        self._settle(game)
        self._close(game)
        await self._show(game, me, respond)
        # сопернику — правка его сообщения и новое сообщение с итогом (уведомление)
        await self._push(game, other)
        await self._send(other, self._notice_screen(game, other))

    # --- таймеры ---

    def _schedule(self, game: mp.MpGame) -> None:
        if game.status == mp.ACTIVE and game.time_limit:
            old = self.turn_tasks.pop(game.code, None)
            if old is not None and not old.done():
                old.cancel()
            self.turn_tasks[game.code] = self.mgr._spawn(self._turn_timer(game, game.turn_no))
        if game.status == mp.PLACING:
            for side in game.sides:
                key = (game.code, side.user_id)
                if not side.ready and (key not in self.placement_tasks or self.placement_tasks[key].done()):
                    self.placement_tasks[key] = self.mgr._spawn(self._placement_timer(game, side.user_id))

    def _alive(self, game: mp.MpGame) -> bool:
        return self.games.get(game.code) is game

    async def _turn_timer(self, game: mp.MpGame, turn_no: int) -> None:
        tick = turn_tick(game.time_limit)
        while True:
            left = game.seconds_left(self.mgr.clock())
            if left is None:
                return
            await self.mgr.sleep(min(tick, left))
            async with self.locks[game.code]:
                if not self._alive(game) or game.status != mp.ACTIVE or game.turn_no != turn_no:
                    return
                now = self.mgr.clock()
                if game.seconds_left(now) <= 0:
                    over = game.timeout(now)
                    if over:
                        self._settle(game)
                        self._close(game)
                    self._save(game)
                    for side in game.sides:
                        await self._push(game, side)
                    if not over:
                        self.turn_tasks.pop(game.code, None)
                        self._schedule(game)
                    return
                for side in game.sides:
                    await self._push(game, side)

    async def _placement_timer(self, game: mp.MpGame, user_id: int) -> None:
        while True:
            side = game.side(user_id)
            if not self._alive(game) or game.status != mp.PLACING or side.ready:
                return
            left = side.placement_deadline - self.mgr.clock()
            if left > 0:
                await self.mgr.sleep(min(PLACEMENT_TICK, left))
            async with self.locks[game.code]:
                if not self._alive(game) or game.status != mp.PLACING or side.ready:
                    return
                now = self.mgr.clock()
                if side.placement_deadline - now > 0:
                    await self._push(game, side)
                    continue
                game.end(None, mp.END_PLACEMENT_TIMEOUT, now)
                self._close(game)
                for s in game.sides:
                    await self._push_screen(game, s, self._info_screen(t("mp_placement_timeout")))
                return

    async def _animate(self, game: mp.MpGame, attacker: int, cells: List[sea.Cell], moves_seen: int) -> None:
        """Мигание потопленного корабля у обоих. Ходы не блокирует: если кто-то успел
        выстрелить, оставшиеся кадры пропускаются. После последнего корабля — итог."""
        final = game.code in self.animating
        self.blinking[game.code] += 1
        try:
            for i in range(BLINKS * 2):
                symbol = SEA_SYMBOLS[sea.SHOT_HIT] if i % 2 == 0 else SEA_SYMBOLS[sea.SHOT_SUNK]
                async with self.locks[game.code]:
                    if len(game.moves) != moves_seen or not (self._alive(game) or final):
                        break
                    for side in game.sides:
                        await self._push(game, side, highlight=(attacker, set(cells), symbol))
                await self.mgr.sleep(self.mgr.mp_blink_seconds)
        finally:
            self.blinking[game.code] -= 1
            async with self.locks[game.code]:
                if final:
                    self.animating.discard(game.code)
                    self._close(game)
                    for side in game.sides:
                        await self._push(game, side)
                elif self._alive(game) and len(game.moves) == moves_seen:
                    for side in game.sides:
                        await self._push(game, side)

    # --- итог ---

    def _settle(self, game: mp.MpGame) -> None:
        """Рейтинг Elo по итогу партии: пишется сразу, до анимации — рестарт его не потеряет."""
        if game.winner is None or game.guest is None:
            return
        gtype = mp.game_type(game.ship_set)
        winner, loser = game.side(game.winner), game.opponent(game.winner)
        storage, platform, now = self.mgr.storage, self.mgr.platform, self.mgr.clock()
        rw = storage.rating(platform, winner.user_id, gtype, mp.ELO_START)
        rl = storage.rating(platform, loser.user_id, gtype, mp.ELO_START)
        delta = mp.elo_delta(rw, rl)
        winner.rating, winner.rating_delta = rw + delta, delta
        loser.rating, loser.rating_delta = rl - delta, -delta
        for s in game.sides:
            storage.upsert_user(platform, s.user_id, s.name, s.chat_id, now)
        storage.save_match(platform, gtype, winner.user_id, loser.user_id,
                           {winner.user_id: winner.rating, loser.user_id: loser.rating}, now)

    def _close(self, game: mp.MpGame) -> None:
        """Партия кончилась: в БД — итог, из памяти и таймеров — вон (если не мигает последний корабль)."""
        self._save(game)
        if game.code in self.animating:
            return
        self.games.pop(game.code, None)
        task = self.turn_tasks.pop(game.code, None)
        if task is not None and not task.done() and task is not asyncio.current_task():
            task.cancel()
        for side in game.sides:
            task = self.placement_tasks.pop((game.code, side.user_id), None)
            if task is not None and not task.done() and task is not asyncio.current_task():
                task.cancel()

    def _save(self, game: mp.MpGame) -> None:
        self.mgr.storage.save_mp(self.mgr.platform, game.code, game.status, game.to_dict(), self.mgr.clock())

    def restore(self) -> int:
        """После перезапуска: открытые партии из БД и их таймеры. Возвращает их число."""
        for d in self.mgr.storage.load_mp(self.mgr.platform, mp.OPEN):
            game = mp.MpGame.from_dict(d)
            self.games[game.code] = game
            self._schedule(game)
        return len(self.games)

    # --- вывод ---

    async def _show(self, game: mp.MpGame, side: mp.Side, respond, note: Optional[str] = None) -> None:
        """Ответ игроку: экран партии; сообщение, где он нажал, становится сообщением партии."""
        ref = await respond(Reply(self.screen(game, side), note))
        if ref is not None:
            side.msg_ref = ref
            self._save(game)

    async def _push(self, game: mp.MpGame, side: mp.Side, highlight=None) -> None:
        await self._push_screen(game, side, self.screen(game, side, highlight))

    async def _push_screen(self, game: mp.MpGame, side: mp.Side, screen: Screen) -> None:
        if side.msg_ref is None:
            return
        try:
            await self.mgr.push(side.msg_ref, screen)
        except Exception:
            logger.exception("mp push failed: game %s user %s", game.code, side.user_id)

    async def _send(self, side: mp.Side, screen: Screen):
        if self.mgr.send is None or side.chat_id is None:
            return None
        try:
            return await self.mgr.send(side.chat_id, screen)
        except Exception:
            logger.exception("mp send failed: user %s", side.user_id)
            return None

    async def _move_to_new_message(self, game: mp.MpGame, side: mp.Side, intro: str) -> None:
        """Событие соперника (подключился, расставил корабли): старое сообщение — короткой
        строкой, партия — новым сообщением, чтобы игроку пришло уведомление."""
        await self._push_screen(game, side, Screen(intro, [menu_row()]))
        ref = await self._send(side, self.screen(game, side))
        if ref is not None:
            side.msg_ref = ref
            self._save(game)

    # --- экраны ---

    def screen(self, game: mp.MpGame, side: mp.Side, highlight=None) -> Screen:
        if game.status == mp.WAITING:
            return self._invite_screen(game)
        if game.status == mp.PLACING:
            return self._placement_screen(game, side)
        if game.status == mp.CANCELLED:
            key = "mp_placement_timeout" if game.end_reason == mp.END_PLACEMENT_TIMEOUT else "mp_invite_cancelled"
            return self._info_screen(t(key))
        return self._board_screen(game, side, highlight)

    def _invite_screen(self, game: mp.MpGame) -> Screen:
        text = t("mp_invite", link=self.mgr.invite_link(game.code), code=game.code,
                 time=t(f"mp_time_{game.time_limit}"), set=t(f"mp_set_{game.ship_set}"),
                 mode=t(f"mp_mode_{game.mode}"))
        return Screen(text, [[Button(t("btn_mp_cancel_invite"), data("mpx", game.code))], menu_row()])

    def _placement_screen(self, game: mp.MpGame, side: mp.Side) -> Screen:
        surrender = [Button(t("btn_surrender"), data("mpg", game.code))]
        if side.ready:
            return Screen(t("mp_waiting_ready"), [surrender, menu_row()])
        p = side.placement
        current, fixed, forbidden = set(p.current_cells()), p.fixed_cells(), p.forbidden()
        lines = []
        for i, size in enumerate(p.sizes):
            mark = "✅" if i < len(p.fixed) else ("👉" if i == len(p.fixed) else "⬜")
            lines.append(f"{mark} {'▮' * size} ({size})")
        left = side.placement_deadline - self.mgr.clock()
        text = "\n".join([t("mp_placement"), "", *lines, "", t("mp_placement_timer", left=fmt_left(max(0, left)))])

        def symbol(r, c):
            if (r, c) in fixed:
                return OWN_SHIP
            if (r, c) in current:
                return PLACE_CURRENT
            if (r, c) in forbidden:
                return PLACE_FORBIDDEN
            return SEA_SYMBOLS[sea.UNKNOWN]
        rows = [[Button(symbol(r, c), data("mpp", game.code, r, c)) for c in range(sea.COLS)]
                for r in range(sea.ROWS)]
        if p.current_cells():
            rows.append([Button(t("btn_mp_fix"), data("mpk", game.code))])
        elif p.is_complete():
            rows.append([Button(t("btn_mp_ready"), data("mpy", game.code))])
        rows.append([Button(t("btn_mp_reset"), data("mpz", game.code))])
        rows.append(surrender + menu_row())
        return Screen(text, rows)

    def _move_line(self, game: mp.MpGame, side: mp.Side, move: dict) -> str:
        key = {sea.MISS: "mp_result_miss", sea.HIT: "mp_result_hit"}.get(move["result"], "mp_result_sunk")
        who = "mp_move_me" if move["by"] == side.user_id else "mp_move_them"
        return t(who, result=t(key))

    def _result_lines(self, game: mp.MpGame, side: mp.Side) -> List[str]:
        won = game.winner == side.user_id
        key = {mp.END_TIMEOUTS: ("mp_win_timeouts", "mp_loss_timeouts"),
               mp.END_SURRENDER: ("mp_win_surrender", "mp_loss_surrender")}.get(game.end_reason, ("mp_win", "mp_loss"))
        lines = [t(key[0] if won else key[1], score=side.score, max=mp.MAX_TIMEOUTS)]
        if side.rating is not None:
            lines.append(t("mp_rating", rating=side.rating, delta=f"{side.rating_delta:+d}"))
        return lines

    def _notice_screen(self, game: mp.MpGame, side: mp.Side) -> Screen:
        return Screen("\n".join(self._result_lines(game, side)),
                      [[Button(t("btn_mp_again"), "mp")], menu_row()])

    def _board_screen(self, game: mp.MpGame, side: mp.Side, highlight=None) -> Screen:
        other = game.opponent(side.user_id)
        now = self.mgr.clock()
        result_shown = game.status == mp.FINISHED and game.code not in self.animating
        lines = [t("mp_versus", name=html.escape(other.name, quote=False), set=t(f"mp_set_{game.ship_set}"))]
        lines += [self._move_line(game, side, m) for m in game.last_moves()]
        if result_shown:
            lines += self._result_lines(game, side)
        elif game.status == mp.FINISHED:
            lines.append(t("mp_game_over"))
        else:
            turn = t("mp_your_turn") if game.turn == side.user_id else t("mp_their_turn")
            left = game.seconds_left(now)
            if left is not None:
                turn += t("mp_timer", left=fmt_left(left))
            lines.append(turn)
            if side.timeouts or other.timeouts:
                lines.append(t("mp_timeouts", mine=side.timeouts, theirs=other.timeouts,
                               name=html.escape(other.name, quote=False), max=mp.MAX_TIMEOUTS))
        hl_cells = highlight[1] if highlight else set()
        hl_symbol = highlight[2] if highlight else None
        own_hl = highlight is not None and highlight[0] == other.user_id
        attack_hl = highlight is not None and highlight[0] == side.user_id

        # своё поле — текстом: мои корабли и выстрелы соперника
        their_shots = other.shots
        grid = []
        for r in range(sea.ROWS):
            row = ""
            for c in range(sea.COLS):
                shot = their_shots[r][c] if their_shots else sea.UNKNOWN
                if own_hl and (r, c) in hl_cells:
                    row += hl_symbol
                elif shot != sea.UNKNOWN:
                    row += SEA_SYMBOLS[shot]
                else:
                    row += OWN_SHIP if any((r, c) in ship for ship in side.ships) else SEA_SYMBOLS[sea.UNKNOWN]
            grid.append(row)
        lines += ["", t("mp_own_field"), *grid, ""]
        lines.append(t("mp_enemy_field") if result_shown else t("mp_attack_hint"))

        # поле соперника — кнопками; после итога видны его непотопленные корабли
        enemy_ships = {cell for ship in other.ships for cell in ship}

        def symbol(r, c):
            if attack_hl and (r, c) in hl_cells:
                return hl_symbol
            shot = side.shots[r][c]
            if result_shown and shot == sea.UNKNOWN and (r, c) in enemy_ships:
                return OWN_SHIP
            return SEA_SYMBOLS[shot]
        payload = (lambda r, c: "noop") if result_shown else (lambda r, c: data("mpf", game.code, r, c))
        rows = [[Button(symbol(r, c), payload(r, c)) for c in range(sea.COLS)] for r in range(sea.ROWS)]
        if result_shown:
            rows.append([Button(t("btn_mp_again"), "mp")])
            rows.append(menu_row())
        elif game.status == mp.ACTIVE:
            rows.append([Button(t("btn_surrender"), data("mpg", game.code))] + menu_row())
        else:
            rows.append(menu_row())
        return Screen("\n".join(lines), rows)

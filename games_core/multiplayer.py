"""Морской бой с другом и с компьютером: нажатия, экраны и таймеры. Правила — seafight_mp,
ходы компьютера — sea_ai (он видит только свою сетку выстрелов).

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
  mpp:<код>:<r>:<c>:<h|v>  поставить корабль центром в клетку сразу с ориентацией (Mini App)
  mpg:<код>                сдаться (до начала боя — отменить партию)
  mpb                      вернуться к своей партии
  ai                       бой с компьютером: выбор сложности
  ain:<уровень>[:<сек>[:<набор>[:<расстановка>]]]  шаги выбора; последний сразу начинает партию
"""
import asyncio
import contextlib
import html
import logging
import random
from collections import defaultdict
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from . import motivation
from . import sea_ai
from . import seafight_mp as mp
from . import seafight_solo as sea
from .sessions import SEA_SYMBOLS, Player
from .texts import TITLES, t
from .ui import Button, Reply, Screen, data

if TYPE_CHECKING:
    from .manager import Manager

logger = logging.getLogger(__name__)

ACTIONS = ("mp", "mpn", "mpj", "mpx", "mpf", "mpp", "mpk", "mpz", "mpy", "mpg", "mpb", "ai", "ain")

OWN_SHIP = "🔳"
PLACE_CURRENT = "🔲"
PLACE_FORBIDDEN = "🟩"
BLINKS = 3                 # мигание потопленного корабля: 3 раза 💢 ↔ 💥
PLACEMENT_TICK = 30        # как часто обновлять таймер расстановки


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


def again_button(vs_ai: bool) -> Button:
    """Новая партия того же рода: с компьютером или с другом."""
    return Button(t("btn_ai_again"), "ai") if vs_ai else Button(t("btn_mp_again"), "mp")


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

        if action in ("mp", "mpn", "mpj", "ai", "ain"):
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
        elif action == "ai":
            await respond(Reply(self._busy_screen(player) or self._ai_level_screen()))
        elif action == "ain":
            await self._ai_wizard(player, args, respond)
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
            if action == "mpp" and len(args) > 2:
                if args[2] not in ("h", "v"):
                    await respond(Reply(note=t("note_stale")))
                    return
                cell = (*cell, args[2] == "v")
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

    def _time_screen(self, title: str = "mp_title", prefix: tuple = ("mpn",)) -> Screen:
        def b(sec):
            return Button(t(f"mp_time_{sec}"), data(*prefix, sec))
        return Screen(f"{t(title)}\n\n{t('mp_choose_time')}", [
            [b(0)], [b(10), b(30)], [b(60), b(300)], [b(3600)],
            [Button(t("btn_cancel"), "sea")],
        ])

    def _set_screen(self, title: str, prefix: tuple) -> Screen:
        return Screen(f"{t(title)}\n\n{t('mp_choose_set')}", [
            [Button(t("btn_sea_full"), data(*prefix, "full"))],
            [Button(t("btn_sea_reduced"), data(*prefix, "reduced"))],
            [Button(t("btn_cancel"), "sea")],
        ])

    def _mode_screen(self, title: str, prefix: tuple) -> Screen:
        return Screen(f"{t(title)}\n\n{t('mp_choose_mode')}", [
            [Button(t("btn_mp_auto"), data(*prefix, mp.AUTO))],
            [Button(t("btn_mp_manual"), data(*prefix, mp.MANUAL))],
            [Button(t("btn_cancel"), "sea")],
        ])

    def _ai_level_screen(self) -> Screen:
        return Screen(f"{t('ai_title')}\n\n{t('ai_choose_level')}", [
            [Button(t("btn_ai_normal"), data("ain", sea_ai.NORMAL))],
            [Button(t("btn_ai_advanced"), data("ain", sea_ai.ADVANCED))],
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
        if ship_set is None:
            await respond(Reply(self._set_screen("mp_title", ("mpn", limit))))
            return
        if mode is None:
            await respond(Reply(self._mode_screen("mp_title", ("mpn", limit, ship_set))))
            return
        code = self._new_code()
        now = self.mgr.clock()
        game = mp.MpGame(code, ship_set, mode, limit, self._side(player), created_at=now)
        self.games[code] = game
        async with self.locks[code]:
            self._save(game)
            await self._show(game, game.host, respond)

    async def _ai_wizard(self, player: Player, args: List[str], respond) -> None:
        """Сложность → время на ход → набор → расстановка; последний шаг сразу начинает партию."""
        level = args[0] if args else None
        try:
            limit = int(args[1]) if len(args) > 1 else None
        except ValueError:
            limit = -1
        ship_set = args[2] if len(args) > 2 else None
        mode = args[3] if len(args) > 3 else None
        if level not in sea_ai.LEVELS or (limit is not None and limit not in mp.TIME_LIMITS) \
                or (ship_set and ship_set not in sea.SHIP_SETS) or (mode and mode not in (mp.AUTO, mp.MANUAL)):
            await respond(Reply(self._ai_level_screen()))
            return
        busy = self._busy_screen(player)
        if busy:
            await respond(Reply(busy))
            return
        if limit is None:
            await respond(Reply(self._time_screen("ai_title", ("ain", level))))
            return
        if ship_set is None:
            await respond(Reply(self._set_screen("ai_title", ("ain", level, limit))))
            return
        if mode is None:
            await respond(Reply(self._mode_screen("ai_title", ("ain", level, limit, ship_set))))
            return
        code = self._new_code()
        now = self.mgr.clock()
        game = mp.MpGame(code, ship_set, mode, limit, self._side(player), created_at=now, ai_level=level)
        game.join_ai(t("ai_name", level=t(f"ai_level_{level}")), now, self.mgr.rng)
        self.games[code] = game
        async with self.locks[code]:
            self._save(game)
            await self._show(game, game.host, respond)
            self._schedule(game)

    def debug_ai_game(self, player: Player, ship_set: str) -> Screen:
        """/dbg sea_end: бой с компьютером, где игроку остался один выстрел до победы."""
        busy = self._busy_screen(player)
        if busy:
            return busy
        now = self.mgr.clock()
        game = mp.MpGame(self._new_code(), ship_set, mp.AUTO, 0, self._side(player), created_at=now,
                         ai_level=sea_ai.NORMAL)
        game.join_ai(t("ai_name", level=t("ai_level_normal")), now, self.mgr.rng)
        board = game.target(player.user_id)
        cells = [cell for ship in board.ships for cell in ship]
        for r, c in cells[:-1]:
            board.fire(r, c)
        self.games[game.code] = game
        self._save(game)
        return self.screen(game, game.host)

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

    def _info_screen(self, text: str, extra: Optional[List[List[Button]]] = None, vs_ai: bool = False) -> Screen:
        again = Button(t("btn_ai"), "ai") if vs_ai else Button(t("btn_mp"), "mp")
        return Screen(text, (extra or []) + [[again], menu_row()])

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
            error = p.tap(*cell) if len(cell) == 2 else p.place(*cell)
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
                if not game.vs_ai:
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
            await respond(Reply(self._info_screen(t("mp_cancelled_you"), vs_ai=game.vs_ai)))
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
        """Задача текущего хода: ход компьютера или таймер хода игрока; таймеры расстановки."""
        if game.status == mp.ACTIVE and (game.time_limit or game.is_ai(game.turn)):
            old = self.turn_tasks.pop(game.code, None)
            if old is not None and not old.done() and old is not asyncio.current_task():
                old.cancel()
            job = self._ai_move if game.is_ai(game.turn) else self._turn_timer
            self.turn_tasks[game.code] = self.mgr._spawn(job(game, game.turn_no))
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

    async def _ai_move(self, game: mp.MpGame, turn_no: int) -> None:
        """Ход компьютера: «думает» ai_think_seconds, стреляет по своей сетке выстрелов."""
        await self.mgr.sleep(self.mgr.ai_think_seconds)
        async with self.locks[game.code]:
            if not self._alive(game) or game.status != mp.ACTIVE or game.turn_no != turn_no:
                return
            ai = game.side(mp.AI_USER_ID)
            # расчёт идёт в другом потоке: ему — копия сетки и свой генератор случайных чисел
            shots = [list(row) for row in ai.shots]
            rng = random.Random(self.mgr.rng.random())
            r, c = await self.mgr.run_cpu(sea_ai.choose_shot, shots, list(game.sizes), game.ai_level, rng)
            if not self._alive(game) or game.status != mp.ACTIVE or game.turn_no != turn_no:
                return
            result = game.fire(ai.user_id, r, c, self.mgr.clock())
            if result == sea.IGNORED:          # не должно случаться: sea_ai стреляет только в новые клетки
                logger.error("ai shot ignored: game %s cell %s", game.code, (r, c))
                game.pass_turn(self.mgr.clock())
                self._save(game)
                self.turn_tasks.pop(game.code, None)
                self._schedule(game)
                return
            sunk = game.ship_cells_sunk_by(game.moves[-1]) if result in (sea.SUNK, sea.WON) else []
            if result == sea.WON:
                self._settle(game)
                self.animating.add(game.code)
            self._save(game)
            await self._push(game, game.human)
            if sunk:
                self.mgr._spawn(self._animate(game, ai.user_id, sunk, len(game.moves)))
            if result != sea.WON:
                self.turn_tasks.pop(game.code, None)
                self._schedule(game)

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
                    await self._push_screen(game, s, self._info_screen(t("mp_placement_timeout"), vs_ai=game.vs_ai))
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
        if game.vs_ai:
            self._settle_ai(game)
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

    def _settle_ai(self, game: mp.MpGame) -> None:
        """Бой с компьютером: без Elo — победа или поражение в таблицу и партия в историю,
        чтобы засчитались путь, серия и тренировка дня. Сдача — поражение."""
        human = game.human
        storage, platform, now = self.mgr.storage, self.mgr.platform, self.mgr.clock()
        storage.upsert_user(platform, human.user_id, human.name, human.chat_id, now)
        before = motivation.journey(storage, platform, human.user_id)
        storage.save_ai_result(platform, human.user_id, game.ai_level, game.ship_set,
                               game.winner == human.user_id, now)
        name = mp.ai_game(game.ship_set)
        storage.add_score(platform, human.user_id, name, max(0, human.score), None, now)
        after = motivation.journey(storage, platform, human.user_id)
        events = motivation.diff(before, after, name)
        human.journey_lines = motivation.result_lines(events, after)
        human.next_training = events.next_training
        self.mgr.partia_saved(human.user_id, events, after)

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
        строкой, партия — новым сообщением, чтобы игроку пришло уведомление.
        В Mini App экран всегда перед глазами — партия просто обновляется на нём."""
        if side.msg_ref is not None and self.mgr.live_ref(side.msg_ref):
            await self._push(game, side)
            return
        await self._push_screen(game, side, Screen(intro, [menu_row()]))
        ref = await self._send(side, self.screen(game, side))
        if ref is not None:
            side.msg_ref = ref
            self._save(game)

    # --- экраны ---

    def screen(self, game: mp.MpGame, side: mp.Side, highlight=None) -> Screen:
        if game.status == mp.CANCELLED:
            return self._cancelled_screen(game)
        if game.status == mp.WAITING:
            screen = self._invite_screen(game)
        elif game.status == mp.PLACING:
            screen = self._placement_screen(game, side)
        else:
            screen = self._board_screen(game, side, highlight)
        screen.view = self.view(game, side, highlight)
        return screen

    def view(self, game: mp.MpGame, side: mp.Side, highlight=None) -> dict:
        """Состояние партии для Mini App (docs/miniapp/tz-m1-core.md §3.3)."""
        other = game.opponent(side.user_id)
        code = game.code
        result_shown = game.status == mp.FINISHED and code not in self.animating
        active = game.status == mp.ACTIVE
        status = "waiting_ready" if game.status == mp.PLACING and side.ready else game.status
        thinking = active and game.is_ai(game.turn)
        left = game.seconds_left(self.mgr.clock()) if active and not thinking else None
        v = {
            "kind": "sea", "code": code, "set": game.ship_set, "status": status,
            "title": TITLES[f"ai_{game.ship_set}" if game.vs_ai else f"mp_{game.ship_set}"],
            "score": side.score,
            "opponent": {"name": other.name, "ai": game.vs_ai} if other else None,
            "turn": ("me" if game.turn == side.user_id else "them") if active else None,
            "thinking": thinking,
            "timer": {"left": int(left + 0.999), "total": game.time_limit} if left is not None else None,
            "timeouts": {"me": side.timeouts, "them": other.timeouts if other else 0, "max": mp.MAX_TIMEOUTS},
            "last": [{"by": "me" if m["by"] == side.user_id else "them",
                      "result": sea.SUNK if m["result"] == sea.WON else m["result"]}
                     for m in game.last_moves()],
            "own": self._own_grid(game, side, other),
            "enemy": self._enemy_grid(side, other, result_shown),
            "blink": None, "result": None, "placement": None, "invite": None,
            "actions": {"fire": data("mpf", code, "{r}", "{c}"), "surrender": data("mpg", code),
                        "place": data("mpp", code, "{r}", "{c}", "{o}"), "fix": data("mpk", code),
                        "reset": data("mpz", code), "ready": data("mpy", code),
                        "cancel_invite": data("mpx", code)},
        }
        if highlight is not None:
            attacker, cells, symbol = highlight
            v["blink"] = {"board": "enemy" if attacker == side.user_id else "own",
                          "cells": sorted([r, c] for r, c in cells),
                          "frame": "hit" if symbol == SEA_SYMBOLS[sea.SHOT_HIT] else "sunk"}
        if result_shown:
            v["result"] = {"won": game.winner == side.user_id, "reason": game.end_reason, "score": side.score,
                           "rating": side.rating, "delta": side.rating_delta, "journey": list(side.journey_lines)}
        if game.status == mp.PLACING and not side.ready:
            p = side.placement
            v["placement"] = {"sizes": list(p.sizes), "fixed": [[list(x) for x in ship] for ship in p.fixed],
                              "current": [list(x) for x in p.current_cells()], "vertical": p.vertical,
                              "forbidden": sorted(list(x) for x in p.forbidden()),
                              "left": max(0, int(side.placement_deadline - self.mgr.clock() + 0.999))}
        if game.status == mp.WAITING:
            v["invite"] = {"link": self.mgr.start_link(f"mp_{code}"), "code": code}
        return v

    @staticmethod
    def _shot_kind(state: str) -> str:
        return {sea.SHOT_MISS: "miss", sea.SHOT_HIT: "hit", sea.SHOT_SUNK: "sunk"}.get(state, "sea")

    def _own_grid(self, game: mp.MpGame, side: mp.Side, other: Optional[mp.Side]) -> dict:
        """Своё поле: свои корабли (на расстановке — уже поставленные) и выстрелы соперника."""
        if side.placement is not None:
            ships = {tuple(x) for ship in side.placement.fixed for x in ship}
        else:
            ships = {tuple(x) for ship in side.ships for x in ship}
        shots = other.shots if other is not None and other.shots else None

        def cell(r, c):
            state = shots[r][c] if shots else sea.UNKNOWN
            if state != sea.UNKNOWN:
                return {"k": self._shot_kind(state)}
            return {"k": "ship" if (r, c) in ships else "sea"}
        return {"rows": sea.ROWS, "cols": sea.COLS,
                "cells": [[cell(r, c) for c in range(sea.COLS)] for r in range(sea.ROWS)]}

    def _enemy_grid(self, side: mp.Side, other: Optional[mp.Side], result_shown: bool) -> dict:
        """Поле соперника: мои выстрелы; после итога — его непотопленные корабли."""
        ships = {tuple(x) for ship in other.ships for x in ship} if other is not None else set()

        def cell(r, c):
            state = side.shots[r][c] if side.shots else sea.UNKNOWN
            if state == sea.UNKNOWN and result_shown and (r, c) in ships:
                return {"k": "ship"}
            return {"k": self._shot_kind(state)}
        return {"rows": sea.ROWS, "cols": sea.COLS,
                "cells": [[cell(r, c) for c in range(sea.COLS)] for r in range(sea.ROWS)]}

    def _cancelled_screen(self, game: mp.MpGame) -> Screen:
        if game.end_reason == mp.END_PLACEMENT_TIMEOUT:
            key = "mp_placement_timeout"
        else:
            key = "mp_cancelled_you" if game.vs_ai else "mp_invite_cancelled"
        return self._info_screen(t(key), vs_ai=game.vs_ai)

    def _invite_screen(self, game: mp.MpGame) -> Screen:
        text = t("mp_invite", link=self.mgr.start_link(f"mp_{game.code}"), code=game.code,
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
        if side.journey_lines:
            lines += [""] + side.journey_lines
        return lines

    def _notice_screen(self, game: mp.MpGame, side: mp.Side) -> Screen:
        return Screen("\n".join(self._result_lines(game, side)),
                      [[again_button(game.vs_ai)], menu_row()])

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
        elif game.is_ai(game.turn):
            lines.append(t("ai_thinking"))
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
            rows.append([again_button(game.vs_ai)])
            if side.next_training:
                rows.append([Button(t("btn_daily_next", title=TITLES[side.next_training]),
                                    motivation.play_payload(side.next_training))])
            rows.append(menu_row())
        elif game.status == mp.ACTIVE:
            rows.append([Button(t("btn_surrender"), data("mpg", game.code))] + menu_row())
        else:
            rows.append(menu_row())
        return Screen("\n".join(lines), rows)

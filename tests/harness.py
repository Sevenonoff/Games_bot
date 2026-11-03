"""Мессенджер без мессенджера: цепочки нажатий через Manager, как их делает человек.

VirtualTime — часы и sleep для Manager: таймеры (отсчёт «3, 2, 1», показ фигур,
ход таймера, конец минуты) срабатывают по advance(), минута партии проходит мгновенно.
Messenger хранит сообщения бота и принимает правки по таймеру (push).
Chat — переписка одного игрока: send() — текстовое сообщение (ответ приходит
новым сообщением), click("подпись") и tap(r, c) — нажатия кнопок текущего экрана.
right_move() подсказывает верный ход, чтобы сценарии доходили до побед и новых уровней.
"""
import asyncio
import heapq
import itertools
import random
import re
from typing import Dict, List, Optional, Tuple

from games_core import friends
from games_core import path
from games_core import seafight_mp as mp
from games_core import seafight_solo as sea
from games_core.manager import RECORD_GAMES, Manager, start_payload
from games_core.sessions import GAMES, INPUT, Player, Session, TimedSession
from games_core.storage import Storage
from games_core.texts import t
from games_core.ui import FIELD_SIDE, Button, Screen
from sea_fight_aiogram import games_menu as tg

Cell = Tuple[int, int]


async def settle(rounds: int = 20) -> None:
    """Дать запущенным задачам (таймерам Manager) доработать до следующего ожидания."""
    for _ in range(rounds):
        await asyncio.sleep(0)


class VirtualTime:
    def __init__(self, start: float = 1_000_000.0):
        self.now = start
        self._timers: List[Tuple[float, int, asyncio.Future]] = []
        self._seq = itertools.count()

    def __call__(self) -> float:
        return self.now

    async def sleep(self, seconds: float) -> None:
        fut = asyncio.get_running_loop().create_future()
        heapq.heappush(self._timers, (self.now + max(0.0, seconds), next(self._seq), fut))
        await fut

    async def advance(self, seconds: float) -> None:
        """Сдвинуть время, по очереди будя таймеры, чей срок наступил."""
        until = self.now + seconds
        await settle()
        while self._timers and self._timers[0][0] <= until:
            wake_at, _, fut = heapq.heappop(self._timers)
            self.now = max(self.now, wake_at)
            if not fut.done():
                fut.set_result(None)
            await settle()
        self.now = until


class Messenger:
    def __init__(self):
        self.screens: Dict[str, Screen] = {}
        self.history: List[Screen] = []     # все версии всех сообщений — для поиска приглашений
        self.pushes = 0
        self._ids = itertools.count(1)

    def new_message(self, screen: Screen) -> str:
        screen.validate()
        ref = f"m{next(self._ids)}"
        self.screens[ref] = screen
        self.history.append(screen)
        return ref

    def edit(self, ref: str, screen: Screen) -> None:
        assert ref in self.screens, f"правка несуществующего сообщения {ref!r}"
        screen.validate()
        self.screens[ref] = screen
        self.history.append(screen)

    async def push(self, ref: str, screen: Screen) -> None:
        self.pushes += 1
        self.edit(ref, screen)


class Chat:
    def __init__(self, mgr: Manager, messenger: Messenger, player: Player):
        self.mgr = mgr
        self.messenger = messenger
        self.player = player
        self.ref: Optional[str] = None     # последнее сообщение бота в чате
        self.note: Optional[str] = None    # всплывающее уведомление последнего нажатия
        self.seen_sent = 0                 # сколько сообщений от бота (World.send) уже проверено

    async def send(self, payload: str = "menu") -> Screen:
        """Текстовое сообщение боту: экран приходит новым сообщением."""
        async def respond(reply):
            if reply.screen is None:
                return None
            self.ref = self.messenger.new_message(reply.screen)
            return self.ref

        self.note = None
        await self.mgr.handle(self.player, payload, respond)
        return self.screen

    async def press(self, payload: str) -> Screen:
        """Нажатие кнопки последнего сообщения: ответ правит его же."""
        assert self.ref is not None, "сначала send()"

        async def respond(reply):
            self.note = reply.note
            if reply.screen is None:
                return None
            self.messenger.edit(self.ref, reply.screen)
            return self.ref

        await self.mgr.handle(self.player, payload, respond)
        return self.screen

    @property
    def screen(self) -> Screen:
        return self.messenger.screens[self.ref]

    @property
    def text(self) -> str:
        return self.screen.text

    @property
    def buttons(self) -> List[Button]:
        return [b for row in self.screen.rows for b in row]

    @property
    def session(self) -> Optional[Session]:
        return self.mgr.sessions.get(self.player.user_id)

    def find(self, text: str) -> Button:
        """Кнопка по подписи: точное совпадение, иначе единственная, где подпись содержит text."""
        found = [b for b in self.buttons if b.text == text] or \
                [b for b in self.buttons if text in b.text]
        if len(found) != 1:
            raise AssertionError(f"кнопка {text!r}: найдено {len(found)}; "
                                 f"на экране {[b.text for b in self.buttons]}\n{self.text}")
        return found[0]

    def cell(self, r: int, c: int) -> Button:
        for b in self.buttons:
            parts = b.data.split(":")
            if parts[0] == "t" and parts[2:] == [str(r), str(c)]:
                return b
        raise AssertionError(f"нет клетки {(r, c)} на экране\n{self.text}")

    async def start(self, start_param: str) -> Screen:
        """Переход по ссылке ?start=… (в Max — событие bot_started): ответ — новым сообщением."""
        return await self.send(start_payload(start_param))

    def mp_cell(self, r: int, c: int) -> Button:
        for b in self.buttons:
            parts = b.data.split(":")
            if parts[0] in ("mpf", "mpp") and parts[2:] == [str(r), str(c)]:
                return b
        raise AssertionError(f"нет клетки {(r, c)} поля боя на экране\n{self.text}")

    async def click(self, text: str) -> Screen:
        return await self.press(self.find(text).data)

    async def tap(self, r: int, c: int) -> Screen:
        if any(b.data.split(":")[0] in ("mpf", "mpp") for b in self.buttons):
            return await self.press(self.mp_cell(r, c).data)
        return await self.press(self.cell(r, c).data)

    async def play_right(self) -> Screen:
        cell = right_move(self.session)
        assert cell is not None, "нет верного хода сейчас"
        return await self.tap(*cell)


def mp_game(chat) -> Optional[mp.MpGame]:
    """Бой с другом, в котором участвует игрок (открытый или с мигающим последним кораблём)."""
    uid = chat.player.user_id
    return next((g for g in chat.mgr.mp.games.values() if g.side(uid) is not None), None)


def mp_targets(game: mp.MpGame, uid: int, ships: bool) -> List[Cell]:
    """Необстрелянные клетки поля соперника: с кораблями (ships) или пустые."""
    side, enemy = game.side(uid), {cell for ship in game.opponent(uid).ships for cell in ship}
    return [(r, c) for r in range(sea.ROWS) for c in range(sea.COLS)
            if side.shots[r][c] == sea.UNKNOWN and ((r, c) in enemy) == ships]


def mp_right_move(chat) -> Optional[Cell]:
    game = mp_game(chat)
    uid = chat.player.user_id
    if game is None or game.status != mp.ACTIVE or game.turn != uid:
        return None
    targets = mp_targets(game, uid, ships=True)
    return targets[0] if targets else None


def right_move(s: Optional[Session]) -> Optional[Cell]:
    """Верное нажатие в текущей партии; None — сейчас нажимать нечего (показ, конец)."""
    if s is None or s.finished or s.over or s.in_done():
        return None
    if isinstance(s, TimedSession):
        if s.phase != INPUT:
            return None
        if s.game == "matrix":
            return min(s.round.targets - s.round.found)
        if s.game == "path":
            return path_next(s.round)
        by_number = {n: cell for cell, n in s.round.cells.items()}
        return by_number[s.round.numbers[s.round.opened]]
    if s.game == "memo":
        b = s.board
        face_up = b.face_up if len(b.face_up) == 1 else []
        if face_up:
            first = face_up[0]
            idx = next(i for i, icon in enumerate(b.cards)
                       if icon == b.cards[first] and i != first)
        else:
            idx = next(i for i in range(len(b.cards)) if i not in b.matched)
        return divmod(idx, b.cols)
    for ship in s.board.ships:
        for r, c in ship:
            if s.board.shots[r][c] == sea.UNKNOWN:
                return r, c
    return None


def path_next(rnd: path.PathRound) -> Optional[Cell]:
    """Проложи дорогу: следующая клетка кратчайшей дороги, которой ещё нет на поле."""
    return next((x for x in rnd.solution if x not in rnd.road), None)


def path_detour(rnd: path.PathRound) -> Optional[List[Cell]]:
    """Дорога от человека к дому длиннее кратчайшей: обход (перебор простых путей)
    или, если обхода нет, кратчайшая дорога и лишняя клетка."""
    a, b = rnd.ends
    goal = set(rnd.neighbors(b))

    def walk(route: List[Cell]) -> Optional[List[Cell]]:
        if route[-1] in goal:
            return route if len(route) > rnd.shortest else None
        for x in rnd.neighbors(route[-1]):
            if rnd.free(x) and x not in route:
                found = walk(route + [x])
                if found:
                    return found
        return None

    for start in sorted(x for x in rnd.neighbors(a) if rnd.free(x)):
        found = walk([start])
        if found:
            return found
    # обхода нет: клетки ставятся в любом порядке, так что лишняя клетка вдали тоже удлиняет дорогу
    cells = [(r, c) for r in range(rnd.rows) for c in range(rnd.cols)]
    extra = next((x for x in cells if rnd.free(x) and x not in rnd.solution), None)
    return [extra] + rnd.solution if extra is not None else None


def path_middle_first(rnd: path.PathRound) -> List[Cell]:
    """Кратчайшая дорога, положенная с середины: от середины к дому, потом от середины к человеку."""
    mid = len(rnd.solution) // 2
    return rnd.solution[mid:] + rnd.solution[:mid][::-1]


def wrong_move(s: TimedSession) -> Cell:
    """Ошибочное нажатие: в матрице — пустая клетка, в поездке на числах — не то число
    (пустые неактивны), в «Проложи дорогу» — препятствие."""
    if s.game == "matrix":
        return next((r, c) for r in range(s.round.rows) for c in range(s.round.cols)
                    if (r, c) not in s.round.targets)
    if s.game == "path":
        return min(s.round.blocks)
    right = right_move(s)
    cell = next((cell for cell in s.round.cells if cell != right and not s.round.is_opened(cell)), None)
    assert cell is not None, "осталось одно число — ошибиться нельзя"
    return cell


def wrong_moves(s: Session) -> List[Cell]:
    """Нажатия, которые дают ошибку: промах в матрице, башне, морском бое; несовпавшая пара в мемо."""
    if isinstance(s, TimedSession):
        return [wrong_move(s)]
    if s.game == "memo":
        b = s.board
        hidden = [i for i in range(len(b.cards)) if i not in b.matched]
        if len(b.face_up) == 1:
            first, taps = b.face_up[0], []
        else:
            first, taps = hidden[0], [hidden[0]]
        second = next((i for i in hidden if b.cards[i] != b.cards[first]), None)
        assert second is not None, "осталась одна пара — ошибиться нельзя"
        return [divmod(i, b.cols) for i in taps + [second]]
    return [next((r, c) for r in range(s.board.rows) for c in range(s.board.cols)
                 if s.board.shots[r][c] == sea.UNKNOWN and s.board.ship_at((r, c)) is None)]


class World:
    """Manager на виртуальном времени, общая БД и чаты игроков."""

    def __init__(self, seed: int = 1, round_seconds: int = 60, preview_seconds: float = 1.0,
                 countdown_seconds: float = 2.0, tick_seconds: float = 5.0, debug_users=(),
                 platform: str = "max"):
        self.time = VirtualTime()
        self.storage = Storage(":memory:")
        self.messenger = Messenger()
        self.platform = platform
        self.chats: Dict[int, "Chat"] = {}       # chat_id → чат: туда приходят сообщения send()
        self.inbox: Dict[int, List[Screen]] = {}  # chat_id → сообщения, которые бот прислал сам
        self.sent_at: List[Tuple[int, float, Screen]] = []   # те же сообщения со временем отправки
        self.errors: List[BaseException] = []   # исключения в таймерах, иначе они пропадут молча
        self.rng = random.Random(seed)
        self._options = dict(preview_seconds=preview_seconds, countdown_seconds=countdown_seconds,
                             tick_seconds=tick_seconds, round_seconds=round_seconds,
                             debug_users=debug_users)
        self.mgr = self._manager()

    def _manager(self) -> Manager:
        host = "https://t.me/test_bot" if self.platform == "tg" else "https://max.ru/test_bot"
        mgr = Manager(self.storage, self.platform, self.messenger.push, clock=self.time,
                      rng=self.rng, sleep=self.time.sleep, send=self.send,
                      start_link=lambda param: f"{host}?start={param}",
                      **self._options)
        spawn = mgr._spawn

        def spawn_watched(coro):
            task = spawn(coro)
            task.add_done_callback(self._collect)
            return task
        mgr._spawn = spawn_watched
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            pass        # World вне цикла событий (синхронный тест): без уведомлений по времени
        else:
            mgr.start_background()
        return mgr

    async def send(self, chat_id: int, screen: Screen) -> str:
        """Бот сам пишет в чат (уведомление): новое сообщение становится последним в чате."""
        ref = self.messenger.new_message(screen)
        self.inbox.setdefault(chat_id, []).append(screen)
        self.sent_at.append((chat_id, self.time.now, screen))
        chat = self.chats.get(chat_id)
        if chat is not None:
            chat.ref = ref
        return ref

    async def restart(self) -> None:
        """Перезапуск бота: таймеры гибнут, БД и сообщения в чатах остаются."""
        await self.mgr.shutdown()
        self.mgr = self._manager()
        self.mgr.restore()
        for chat in self.chats.values():
            chat.mgr = self.mgr
        await settle()

    def _collect(self, task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception() is not None:
            self.errors.append(task.exception())

    def chat(self, user_id: int = 42, name: str = "Тестер") -> Chat:
        chat = Chat(self.mgr, self.messenger, Player(self.platform, user_id, name, chat_id=user_id))
        self.chats[user_id] = chat
        return chat

    def invite_link(self) -> Optional[str]:
        """Параметр start последней ссылки-приглашения (в бой или в друзья), которую бот присылал
        (её могли и переслать)."""
        for screen in reversed(self.messenger.history):
            m = re.search(r"\?start=((?:mp|fr)_[A-Z0-9]+)", screen.text)
            if m:
                return m[1]
        return None

    def scores_count(self) -> int:
        return self.storage.conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]

    async def close(self) -> None:
        await self.mgr.shutdown()
        self.storage.close()


async def wait_preview(world: "World", chat: Chat) -> None:
    """Если идёт отсчёт, показ фигур, разбор или итог — дождаться начала ввода (или конца партии)."""
    s = chat.session
    for _ in range(200):
        if s is None or s.finished:
            return
        if isinstance(s, TimedSession) and s.phase == INPUT:
            return
        if not isinstance(s, TimedSession) and not s.in_done():
            return
        await world.time.advance(0.1)
    raise AssertionError(f"ввод не начался: фаза {getattr(s, 'phase', None)}")


async def win_round(world: "World", chat: Chat) -> Optional[str]:
    """Пройти текущий раунд матрицы, поездки на числах или дороги; партия остаётся на итоге раунда.
    Возвращает уведомление."""
    await wait_preview(world, chat)
    s = chat.session
    while s.phase == INPUT and not s.finished:
        await chat.play_right()
    return chat.note


# --- инварианты: что должно быть верно на любом экране ---

MP_CODE = f"[{mp.CODE_ALPHABET}]{{{mp.CODE_LEN}}}"
FRIEND_CODE = f"[{mp.CODE_ALPHABET}]{{{friends.CODE_LEN}}}"
KNOWN_PAYLOAD = re.compile(
    r"^(menu|sea|sea_rec|rec|noop|dbg(:\w+)*|mp|mpb"
    rf"|fr(:\d+)?|fri|frs:\d+|frj:{FRIEND_CODE}|set(:fn|:rm(:(off|\d+))?)?"
    r"|mpn:\d+(:(full|reduced)(:(auto|manual))?)?"
    rf"|mpj:{MP_CODE}|mp[xkzyg]:{MP_CODE}|mp[fp]:{MP_CODE}:\d+:\d+"
    rf"|rec:({'|'.join(RECORD_GAMES)})|new:({'|'.join(GAMES)})"
    r"|q:[0-9a-f]{6}|b:[0-9a-f]{6}|t:[0-9a-f]{6}:\d+:\d+)$")


def live(chat):
    s = chat.session
    return s if s is not None and not s.finished else None


def check_screen(chat) -> None:
    buttons = chat.buttons
    assert buttons, "экран без кнопок — тупик"
    for b in buttons:
        assert KNOWN_PAYLOAD.match(b.data), f"кнопка {b.text!r} с неизвестным payload {b.data!r}"
    tg.tg_rows(chat.screen)   # тот же экран уходит и в Telegram: его лимиты тоже соблюдены
    assert chat.text.startswith(t("menu").split("\n")[0]) or any(b.data in ("menu", "sea") or b.data.startswith("q:") for b in buttons), \
        "с экрана не уйти в меню"
    check_mp_screen(chat)
    s = live(chat)
    sids = {b.data.split(":")[1] for b in buttons if b.data[:2] in ("t:", "q:", "b:")}
    if s is not None and s.msg_ref is not None and s.msg_ref != chat.ref:
        # партия идёт в сообщении повыше: последним бот прислал другое (уведомление боя с другом)
        assert not sids, "кнопки партии не в её сообщении"
        screen = chat.messenger.screens[s.msg_ref]
        sids = {b.data.split(":")[1] for row in screen.rows for b in row if b.data[:2] in ("t:", "q:", "b:")}
    else:
        screen = chat.screen
    if s is None:
        assert not sids, "кнопки партии на экране без живой партии"
    else:
        assert sids == {s.sid}, f"на экране кнопки чужой партии: {sids} != {s.sid}"
        assert s.progress.level >= 1
        assert screen.rows == s.screen().rows, "сообщение отстало от состояния партии"
        check_field(screen)


def check_field(screen: Screen) -> None:
    """Поле партии — сетка шириной FIELD_SIDE и не ниже FIELD_SIDE рядов: клавиатура не меняет размер."""
    field = [row for row in screen.rows if row[0].data[:2] in ("t:", "b:")]
    assert len(field) >= FIELD_SIDE, f"поле из {len(field)} рядов, меньше {FIELD_SIDE}"
    assert all(len(row) == FIELD_SIDE for row in field), f"ряды поля: {[len(row) for row in field]}"


def check_mp_screen(chat) -> None:
    """Бой с другом: на экране — только своя партия, и сообщение партии не отстаёт от неё."""
    uid = chat.player.user_id
    codes = {b.data.split(":")[1] for b in chat.buttons if b.data.split(":")[0] in ("mpf", "mpp", "mpk", "mpz", "mpy", "mpg", "mpx")}
    games = chat.mgr.mp.games
    for code in codes:
        if code in games:
            assert games[code].side(uid) is not None, f"на экране кнопки чужой партии {code}"
    game = mp_game(chat)
    if game is None or chat.mgr.mp.blinking.get(game.code):
        return
    side = game.side(uid)
    if side.msg_ref == chat.ref and game.status in mp.OPEN + (mp.FINISHED,):
        assert chat.screen.rows == chat.mgr.mp.screen(game, side).rows, "сообщение боя отстало от партии"

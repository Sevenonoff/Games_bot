"""Мессенджер без мессенджера: цепочки нажатий через Manager, как их делает человек.

VirtualTime — часы и sleep для Manager: таймеры (скрыть фигуры, конец минуты)
срабатывают по advance(), минута партии проходит мгновенно.
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

from games_core import seafight_solo as sea
from games_core.manager import RECORD_GAMES, Manager
from games_core.sessions import GAMES, PREVIEW, Player, Session, TimedSession
from games_core.storage import Storage
from games_core.texts import t
from games_core.ui import Button, Screen

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
        self.pushes = 0
        self._ids = itertools.count(1)

    def new_message(self, screen: Screen) -> str:
        screen.validate()
        ref = f"m{next(self._ids)}"
        self.screens[ref] = screen
        return ref

    def edit(self, ref: str, screen: Screen) -> None:
        assert ref in self.screens, f"правка несуществующего сообщения {ref!r}"
        screen.validate()
        self.screens[ref] = screen

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

    async def click(self, text: str) -> Screen:
        return await self.press(self.find(text).data)

    async def tap(self, r: int, c: int) -> Screen:
        return await self.press(self.cell(r, c).data)

    async def play_right(self) -> Screen:
        cell = right_move(self.session)
        assert cell is not None, "нет верного хода сейчас"
        return await self.tap(*cell)


def right_move(s: Optional[Session]) -> Optional[Cell]:
    """Верное нажатие в текущей партии; None — сейчас нажимать нечего (показ, конец)."""
    if s is None or s.finished or s.over:
        return None
    if isinstance(s, TimedSession):
        if s.phase == PREVIEW:
            return None
        if s.game == "matrix":
            return min(s.round.targets - s.round.found)
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


def wrong_move(s: TimedSession) -> Cell:
    """Ошибочное нажатие в матрице или башне."""
    right = s.round.targets if s.game == "matrix" else {right_move(s)}
    return next((r, c) for r in range(s.round.rows) for c in range(s.round.cols)
                if (r, c) not in right)


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
                 debug_users=()):
        self.time = VirtualTime()
        self.storage = Storage(":memory:")
        self.messenger = Messenger()
        self.mgr = Manager(self.storage, "max", self.messenger.push, clock=self.time,
                           rng=random.Random(seed), sleep=self.time.sleep,
                           preview_seconds=preview_seconds, round_seconds=round_seconds,
                           debug_users=debug_users)
        self.errors: List[BaseException] = []   # исключения в таймерах, иначе они пропадут молча
        spawn = self.mgr._spawn

        def spawn_watched(coro):
            task = spawn(coro)
            task.add_done_callback(self._collect)
            return task
        self.mgr._spawn = spawn_watched

    def _collect(self, task: asyncio.Task) -> None:
        if not task.cancelled() and task.exception() is not None:
            self.errors.append(task.exception())

    def chat(self, user_id: int = 42, name: str = "Тестер") -> Chat:
        return Chat(self.mgr, self.messenger, Player("max", user_id, name, chat_id=user_id))

    def scores_count(self) -> int:
        return self.storage.conn.execute("SELECT COUNT(*) FROM scores").fetchone()[0]

    async def close(self) -> None:
        await self.mgr.shutdown()
        self.storage.close()


async def wait_preview(world: "World", chat: Chat) -> None:
    """Если идёт показ фигур — дождаться его конца."""
    s = chat.session
    if isinstance(s, TimedSession) and not s.finished and s.phase == PREVIEW:
        await world.time.advance(world.mgr.preview_seconds)


async def win_round(world: "World", chat: Chat) -> Optional[str]:
    """Пройти текущий раунд матрицы или башни. Возвращает уведомление."""
    await wait_preview(world, chat)
    s = chat.session
    first = s.round_id
    while s.round_id == first and not s.finished:
        await chat.play_right()
    return chat.note


# --- инварианты: что должно быть верно на любом экране ---

KNOWN_PAYLOAD = re.compile(
    r"^(menu|sea|rec|noop|dbg(:\w+)*"
    rf"|rec:({'|'.join(RECORD_GAMES)})|new:({'|'.join(GAMES)})"
    r"|q:[0-9a-f]{6}|t:[0-9a-f]{6}:\d+:\d+)$")


def live(chat):
    s = chat.session
    return s if s is not None and not s.finished else None


def check_screen(chat) -> None:
    buttons = chat.buttons
    assert buttons, "экран без кнопок — тупик"
    for b in buttons:
        assert KNOWN_PAYLOAD.match(b.data), f"кнопка {b.text!r} с неизвестным payload {b.data!r}"
    assert chat.text == t("menu") or any(b.data == "menu" or b.data.startswith("q:") for b in buttons), \
        "с экрана не уйти в меню"
    s = live(chat)
    sids = {b.data.split(":")[1] for b in buttons if b.data[:2] in ("t:", "q:")}
    if s is None:
        assert not sids, "кнопки партии на экране без живой партии"
    else:
        assert sids == {s.sid}, f"на экране кнопки чужой партии: {sids} != {s.sid}"
        assert s.progress.level >= 1
        assert chat.screen.rows == s.screen().rows, "сообщение отстало от состояния партии"

import asyncio
import random

import pytest

from games_core.manager import Manager
from games_core.progression import Progress
from games_core.sessions import COUNTDOWN, GAMES, INPUT, REVIEW, Player
from games_core.storage import Storage

PLAYER = Player("max", 42, "Тестер", chat_id=7)


class FakeTransport:
    def __init__(self):
        self.replies = []
        self.pushes = []

    async def respond(self, reply):
        self.replies.append(reply)
        return "mid-1"

    async def push(self, ref, screen):
        self.pushes.append((ref, screen))

    @property
    def last(self):
        return self.replies[-1]


@pytest.fixture
async def env():
    storage = Storage(":memory:")
    tr = FakeTransport()
    mgr = Manager(storage, "max", tr.push, rng=random.Random(1),
                  preview_seconds=0.01, countdown_seconds=0.03, review_seconds=0.02, round_seconds=0.2)
    yield mgr, tr, storage
    await mgr.shutdown()


async def press(mgr, tr, payload):
    await mgr.handle(PLAYER, payload, tr.respond)
    return tr.last


def tap_payload(s, r, c):
    return f"t:{s.sid}:{r}:{c}"


async def test_menu_and_screens_valid(env):
    mgr, tr, _ = env
    for payload in ("menu", "sea", "rec", "rec:matrix", "garbage"):
        (await press(mgr, tr, payload)).screen.validate()


async def test_matrix_preview_then_hide_and_timeout(env):
    mgr, tr, storage = env
    reply = await press(mgr, tr, "new:matrix")
    s = mgr.sessions[PLAYER.user_id]
    assert s.phase == COUNTDOWN and s.msg_ref == "mid-1"
    reply.screen.validate()

    # нажатие во время отсчёта не засчитывается
    assert (await press(mgr, tr, tap_payload(s, 0, 0))).note == "Приготовьтесь…"

    await asyncio.sleep(0.1)
    assert s.phase == INPUT and tr.pushes[-1][0] == "mid-1"

    target = sorted(s.round.targets)[0]
    await press(mgr, tr, tap_payload(s, *target))
    assert s.score == 10

    await asyncio.sleep(0.25)
    assert s.finished
    assert "Партия окончена" in tr.pushes[-1][1].text
    assert storage.top("max", "matrix") == [(42, "Тестер", 10)]


async def test_stale_session_rejected(env):
    mgr, tr, _ = env
    await press(mgr, tr, "new:tower")
    old = mgr.sessions[PLAYER.user_id]
    await press(mgr, tr, "new:tower")
    assert (await press(mgr, tr, tap_payload(old, 0, 0))).note == "Эта партия уже завершена"


async def test_tower_round_fail_moves_on(env):
    mgr, tr, _ = env
    await press(mgr, tr, "new:tower")
    s = mgr.sessions[PLAYER.user_id]
    await asyncio.sleep(0.1)
    by_num = {n: cell for cell, n in s.round.cells.items()}
    wrong = by_num[s.round.numbers[-1]]
    first_round = s.round_id
    reply = await press(mgr, tr, tap_payload(s, *wrong))
    assert "Ошибка" in reply.note
    assert s.round_id == first_round and s.phase == REVIEW and s.wrong_cell == wrong
    await asyncio.sleep(0.03)            # разбор кончился — новый раунд с отсчётом
    assert s.round_id == first_round + 1 and s.phase == COUNTDOWN and s.wrong_cell is None
    assert s.progress.fail_count == 1


async def test_memo_full_board_is_win(env):
    mgr, tr, storage = env
    await press(mgr, tr, "new:memo")
    s = mgr.sessions[PLAYER.user_id]
    b = s.board
    by_icon = {}
    for i, icon in enumerate(b.cards):
        by_icon.setdefault(icon, []).append(i)
    for a, c in by_icon.values():
        await press(mgr, tr, tap_payload(s, a // b.cols, a % b.cols))
        reply = await press(mgr, tr, tap_payload(s, c // b.cols, c % b.cols))
    assert s.finished and "Поле собрано" in reply.screen.text
    # 3 пары без промахов на 1 уровне: 10 + 10 + 10
    assert s.score == 30
    # 3 хода при лимите 6 — сразу следующий уровень
    p = storage.load_progress("max", 42, "memo")
    assert p.level == 2 and p.last_success_level == 2 and p.best_score == 30


async def test_memo_quit_is_fail_and_next_partia_keeps_level(env):
    mgr, tr, storage = env
    storage.save_result("max", 42, "memo", Progress(level=4, last_success_level=4), None, 0)
    mgr.clock = lambda: 3600.0
    await press(mgr, tr, "new:memo")
    s = mgr.sessions[PLAYER.user_id]
    assert s.progress.level == 4
    await press(mgr, tr, f"q:{s.sid}")
    assert storage.load_progress("max", 42, "memo").fail_count == 1


async def test_sea_quit_not_recorded(env):
    mgr, tr, storage = env
    await press(mgr, tr, "new:sea_reduced")
    s = mgr.sessions[PLAYER.user_id]
    s.screen().validate()
    await press(mgr, tr, tap_payload(s, 0, 0))
    reply = await press(mgr, tr, f"q:{s.sid}")
    assert "не записан" in reply.screen.text
    assert storage.top("max", "sea_reduced") == []


@pytest.mark.parametrize("game", sorted(GAMES))
@pytest.mark.parametrize("level", [1, 5, 15, 40, 70])
def test_game_screens_fit_limits(game, level):
    storage = Storage(":memory:")
    storage.save_result("max", 1, game, Progress(level=level, last_success_level=level), None, 0)
    s = GAMES[game]("abc", Player("max", 1, "x"), storage, random.Random(level), lambda: 1.0)
    s.screen().validate()

"""Мультиплеер морского боя в TG: после потопления последнего корабля ходов больше нет.

Баг: пока мигал последний корабль (~2,4 с), ход уже был у проигравшего, и он успевал
потопить последний корабль победителя — «побил всех, но проиграл».

Нужен aiogram (venv бота):
    sea_fight_aiogram/.venv/bin/python -m pytest tests/test_tg_mp_finish.py
"""
import asyncio
import json
import os
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("aiogram")

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "sea_fight_aiogram"))
os.environ.setdefault("BOT_TOKEN", "123456:TEST")
import main  # noqa: E402
from config import EMPTY, MISS, SHIP  # noqa: E402
from database.multiplayer_models import MultiplayerGame  # noqa: E402
from utils.i18n import get_translation  # noqa: E402

P1, P2 = 1001, 1002


def board(*ships):
    b = [[EMPTY] * main.COLS for _ in range(main.ROWS)]
    for x, y in ships:
        b[y][x] = SHIP
    return json.dumps(b)


class FakeDb:
    def __init__(self):
        self.saved = []

    async def update_multiplayer_game(self, game):
        self.saved.append((game.status, game.current_turn, game.winner_id))

    async def get_active_game_for_user(self, user_id):
        # в БД партия активна, только если последняя запись — active
        if self.saved and self.saved[-1][0] == "active":
            return {"game_id": 1}
        return None


def tap(user_id, x, y, answers):
    async def answer(text=None, show_alert=False):
        answers.append((user_id, text))
    return SimpleNamespace(from_user=SimpleNamespace(id=user_id, language_code="ru"),
                           data=f"mpfire_{x}_{y}", answer=answer, message=None)


@pytest.fixture
def mp(monkeypatch):
    # у каждого по одному однопалубнику: P1 — (0,0), P2 — (5,5)
    game = MultiplayerGame(game_id=1, player1_id=P1, player2_id=P2, status="active",
                           current_turn=P1, board1=board((0, 0)), board2=board((5, 5)),
                           attacks1="[]", attacks2="[]")
    main.active_games.clear()
    main.active_games.update({P1: game, P2: game})
    finished = []

    async def finish(g, winner_id, *a, **kw):
        finished.append(winner_id)
        g.status = "finished"

    async def no_op(*a, **kw):
        return None

    monkeypatch.setattr(main, "db", FakeDb())
    monkeypatch.setattr(main, "update_mp_boards", no_op)
    monkeypatch.setattr(main, "player_profiles", no_op)
    monkeypatch.setattr(main, "finish_mp_game", finish)
    monkeypatch.setattr(main, "start_turn_timer", lambda g: None)
    monkeypatch.setattr(main, "DELAY", 0.05)
    yield game, finished
    main.active_games.clear()


async def test_loser_cannot_fire_during_final_animation(mp):
    game, finished = mp
    answers = []
    await main.handle_mp_fire(tap(P1, 5, 5, answers), None)    # P1 топит последний корабль
    await asyncio.sleep(0)                                     # анимация началась
    await main.handle_mp_fire(tap(P2, 0, 0, answers), None)    # P2 жмёт сразу следом
    await asyncio.sleep(0.5)                                   # анимация и итог

    assert finished == [P1]
    assert json.loads(game.board1)[0][0] == SHIP, "выстрел проигравшего засчитан"
    assert answers[-1] == (P2, get_translation("ru", "error_game_not_active"))
    # в БД партия сразу закрыта, победитель — P1, ход сопернику не передан
    assert main.db.saved[0] == ("finished", P1, P1)


async def test_ordinary_shot_still_passes_turn(mp):
    game, finished = mp
    answers = []
    await main.handle_mp_fire(tap(P1, 3, 3, answers), None)    # промах
    assert game.current_turn == P2 and game.status == "active"
    assert json.loads(game.board2)[3][3] == MISS
    assert finished == []

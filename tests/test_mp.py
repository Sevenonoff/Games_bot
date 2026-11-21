"""Бой с другом: правила (games_core/seafight_mp.py) без мессенджера."""
import json
import random

import pytest

from games_core import seafight_mp as mp
from games_core import seafight_solo as sea

HOST, GUEST = 1, 2


def game(mode=mp.AUTO, limit=0, ship_set="reduced") -> mp.MpGame:
    g = mp.MpGame("ABC234", ship_set, mode, limit, mp.Side(HOST, "Аня", HOST))
    g.join(mp.Side(GUEST, "Боб", GUEST), now=0.0, rng=random.Random(1))
    return g


def ship_cells(g: mp.MpGame, of: int):
    return [cell for ship in g.side(of).ships for cell in ship]


def water(g: mp.MpGame, of: int):
    ships = set(ship_cells(g, of))
    return [(r, c) for r in range(sea.ROWS) for c in range(sea.COLS) if (r, c) not in ships]


def test_elo_symmetric_and_k32():
    assert mp.elo_delta(1000, 1000) == 16
    assert mp.elo_delta(1200, 1000) < 16 < mp.elo_delta(1000, 1200)


def test_auto_join_starts_with_host_turn():
    g = game()
    assert g.status == mp.ACTIVE and g.turn == HOST
    assert sorted(len(s) for s in g.host.ships) == sorted(sea.SHIP_SETS["reduced"])


def test_turn_passes_after_every_shot():
    g = game()
    hit = ship_cells(g, GUEST)[0]
    assert g.fire(HOST, *hit, now=1) in (sea.HIT, sea.SUNK)
    assert g.turn == GUEST
    assert g.fire(GUEST, *water(g, HOST)[0], now=2) == sea.MISS
    assert g.turn == HOST
    assert g.fire(HOST, *hit, now=3) == sea.IGNORED and g.turn == HOST


def test_winning_shot_closes_game_and_keeps_turn():
    """Баг TG до 1.3.1: после победного выстрела ход уходил проигравшему."""
    g = game()
    targets, misses = ship_cells(g, GUEST), iter(water(g, HOST))
    for cell in targets[:-1]:
        g.fire(HOST, *cell, now=1)
        g.fire(GUEST, *next(misses), now=1)
    assert g.fire(HOST, *targets[-1], now=2) == sea.WON
    assert g.status == mp.FINISHED and g.winner == HOST and g.turn == HOST
    assert g.end_reason == mp.END_SUNK


def test_three_timeouts_is_technical_loss():
    g = game(limit=10)
    assert g.seconds_left(5) == 5
    assert not g.timeout(10)                    # хозяин пропустил 1-й
    assert g.turn == GUEST and g.host.timeouts == 1
    assert not g.timeout(20)                    # гость 1-й
    assert not g.timeout(30)                    # хозяин 2-й
    assert not g.timeout(40)                    # гость 2-й
    assert g.timeout(50)                        # хозяин 3-й
    assert g.status == mp.FINISHED and g.winner == GUEST and g.end_reason == mp.END_TIMEOUTS


def test_placement_errors_and_rotation():
    p = mp.Placement([3, 2])
    assert p.tap(0, 0) == mp.OUT_OF_BOUNDS and p.center is None
    assert p.tap(0, 1) is None and p.current_cells() == [(0, 0), (0, 1), (0, 2)]
    assert p.tap(0, 1) == mp.OUT_OF_BOUNDS      # поворот вверх за край
    assert p.tap(1, 1) is None
    assert p.tap(1, 1) is None and p.vertical   # поворот на месте
    assert p.current_cells() == [(0, 1), (1, 1), (2, 1)]
    assert p.fix() and not p.vertical           # следующий корабль снова горизонтальный
    assert p.tap(0, 1) == mp.OVERLAPS
    assert p.tap(1, 2) == mp.TOO_CLOSE
    assert p.tap(5, 4) is None and p.fix() and p.is_complete()


def test_manual_game_starts_when_both_ready():
    g = game(mode=mp.MANUAL)
    assert g.status == mp.PLACING
    assert g.host.placement_deadline == mp.PLACEMENT_SECONDS
    for uid in (HOST, GUEST):
        p = g.side(uid).placement
        for r, c in ((0, 1), (2, 0), (2, 4), (4, 0), (4, 2), (4, 4)):
            assert p.tap(r, c) is None and p.fix()
    assert not g.set_ready(HOST, now=5)
    assert g.set_ready(GUEST, now=6)
    assert g.status == mp.ACTIVE and g.turn == HOST and g.turn_started_at == 6


def test_roundtrip_through_json():
    g = game(mode=mp.MANUAL, limit=30)
    g.host.placement.tap(0, 1)
    g.host.msg_ref = "mid.123"
    restored = mp.MpGame.from_dict(json.loads(json.dumps(g.to_dict())))
    assert restored.to_dict() == g.to_dict()
    assert restored.host.placement.current_cells() == [(0, 0), (0, 1), (0, 2)]


@pytest.mark.parametrize("word, ok", [("ABC234", True), ("abc234", True), ("привет", False),
                                       ("HELLOS", False), ("ABC2345", False), ("ABC0O1", False)])
def test_code_detection(word, ok):
    from games_core.multiplayer import looks_like_code
    assert looks_like_code(word) == ok


def test_placement_with_orientation():
    """Mini App ставит корабль сразу вертикально — даже там, где горизонтально он не встаёт."""
    p = mp.Placement([3, 1])
    assert p.place(3, 6, vertical=False) == mp.OUT_OF_BOUNDS and p.center is None
    assert p.place(3, 6, vertical=True) is None
    assert p.current_cells() == [(2, 6), (3, 6), (4, 6)]
    assert p.fix()
    assert p.place(3, 5, vertical=False) == mp.TOO_CLOSE

import random

import pytest

from games_core import matrix, memo, progression as pr, scoring, seafight_solo as sea, tower
from games_core.ui import MAX_COLS, MAX_ROWS


# --- уровни ---

def test_three_wins_level_up_two_fails_down():
    p = pr.Progress(level=3, last_success_level=3)
    assert pr.register_win(p) == 0
    assert pr.register_win(p) == 0
    assert pr.register_win(p) == 1 and p.level == 4
    assert pr.register_fail(p) == 0
    assert pr.register_fail(p) == -1 and p.level == 3


def test_fail_breaks_win_streak():
    p = pr.Progress(level=2)
    pr.register_win(p)
    pr.register_win(p)
    pr.register_fail(p)
    assert pr.register_win(p) == 0 and p.level == 2


def test_level_never_below_one():
    p = pr.Progress(level=1)
    pr.register_fail(p)
    pr.register_fail(p)
    assert p.level == 1


def test_start_from_last_success_level():
    p = pr.Progress(level=7, last_success_level=6, last_played_at=1000.0)
    assert pr.start_partia(p, now=1000.0 + 3600) == 6
    assert p.level == 6 and p.win_streak == 0


def test_start_minus_three_after_two_days():
    p = pr.Progress(level=8, last_success_level=8, last_played_at=0.0)
    assert pr.start_partia(p, now=pr.IDLE_SECONDS + 1) == 5
    assert p.last_success_level == 5
    p = pr.Progress(level=2, last_success_level=2, last_played_at=0.0)
    assert pr.start_partia(p, now=pr.IDLE_SECONDS + 1) == 1


def test_win_records_success_level():
    p = pr.Progress(level=5, last_success_level=4)
    pr.register_win(p)
    assert p.last_success_level == 5


# --- очки ---

@pytest.mark.parametrize("streak,mult", [(0, 1), (4, 1), (5, 1.5), (9, 1.5), (10, 2), (20, 3), (40, 4), (99, 4)])
def test_combo_multiplier(streak, mult):
    assert scoring.combo_multiplier(streak) == mult


def test_points_scale_with_level():
    assert scoring.tap_points(1, 0) == 10
    assert scoring.tap_points(3, 10) == 60


# --- матрица ---

@pytest.mark.parametrize("level", range(1, 80))
def test_matrix_fits_limits(level):
    rows, cols, n = matrix.matrix_params(level)
    assert cols <= MAX_COLS and rows <= MAX_ROWS - 1
    assert n < rows * cols * 0.5


def test_matrix_round():
    rnd = matrix.MatrixRound.generate(4, random.Random(1))
    targets = sorted(rnd.targets)
    for cell in targets[:-1]:
        assert rnd.tap(*cell) == matrix.HIT
    assert rnd.tap(*targets[0]) == matrix.IGNORED
    assert rnd.tap(*targets[-1]) == matrix.CLEARED
    other = next((r, c) for r in range(rnd.rows) for c in range(rnd.cols) if (r, c) not in rnd.targets)
    assert matrix.MatrixRound(rnd.rows, rnd.cols, set(targets)).tap(*other) == matrix.MISS


# --- башня ---

def test_tower_first_level_is_one_two_three():
    rnd = tower.TowerRound.generate(1, random.Random(0))
    assert rnd.numbers == [1, 2, 3] and rnd.side == 3


@pytest.mark.parametrize("level", range(1, 70))
def test_tower_numbers_ascending_and_fit(level):
    rng = random.Random(level)
    rnd = tower.TowerRound.generate(level, rng)
    assert rnd.numbers == sorted(set(rnd.numbers))
    assert len(rnd.cells) == len(rnd.numbers) <= rnd.side ** 2
    assert rnd.side <= MAX_COLS


def test_tower_harder_levels():
    rng = random.Random(5)
    starts = {tower.make_numbers(3, rng)[0] for _ in range(50)}
    assert min(starts) >= 2
    runs = [tower.make_numbers(5, rng) for _ in range(50)]
    assert any(b - a > 1 for n in runs for a, b in zip(n, n[1:]))


def test_tower_order():
    rnd = tower.TowerRound.generate(2, random.Random(3))
    by_num = {n: cell for cell, n in rnd.cells.items()}
    assert rnd.tap(*by_num[rnd.numbers[1]]) == tower.MISS
    assert rnd.tap(*by_num[rnd.numbers[0]]) == tower.HIT
    assert rnd.tap(*by_num[rnd.numbers[0]]) == tower.IGNORED
    empty = next((r, c) for r in range(rnd.side) for c in range(rnd.side) if (r, c) not in rnd.cells)
    assert rnd.tap(*empty) == tower.MISS


# --- мемо ---

@pytest.mark.parametrize("level", range(1, 30))
def test_memo_fits_limits(level):
    pairs, rows, cols = memo.memo_params(level)
    assert rows * cols == pairs * 2
    assert cols <= MAX_COLS and rows <= MAX_ROWS - 1


def board(cards, cols):
    return memo.MemoBoard(len(cards) // cols, cols, list(cards))


def test_memo_match_and_clear():
    b = board("AABB", 2)
    assert b.tap(0, 0) == memo.OPENED
    assert b.tap(0, 1) == memo.MATCH
    assert b.tap(1, 0) == memo.OPENED
    assert b.tap(1, 1) == memo.CLEARED


def test_memo_blind_miss_not_penalized_seen_miss_penalized():
    b = board("ABAB", 2)          # A . / A .  -> пары по столбцам
    assert b.tap(0, 0) == memo.OPENED
    assert b.tap(0, 1) == memo.MISMATCH and not b.penalized   # обе впервые
    assert b.tap(1, 0) == memo.OPENED                          # закрывает прошлую пару
    assert b.tap(0, 1) == memo.MISMATCH and b.penalized       # B уже видели
    assert b.face_up == [2, 1]


def test_memo_reopen_ignored():
    b = board("AABB", 2)
    b.tap(0, 0)
    assert b.tap(0, 0) == memo.IGNORED


# --- морской бой ---

@pytest.mark.parametrize("ship_set", ["full", "reduced"])
def test_sea_ships_do_not_touch(ship_set):
    for seed in range(30):
        ships = sea.generate_ships(sea.SHIP_SETS[ship_set], random.Random(seed))
        assert sorted(len(s) for s in ships) == sorted(sea.SHIP_SETS[ship_set])
        for i, a in enumerate(ships):
            for b in ships[i + 1:]:
                assert all(abs(r1 - r2) > 1 or abs(c1 - c2) > 1 for r1, c1 in a for r2, c2 in b)


def test_sea_fire():
    b = sea.SeaBoard([[(0, 0), (0, 1)], [(3, 3)]])
    assert b.fire(5, 5) == sea.MISS and b.score == -1
    assert b.fire(5, 5) == sea.IGNORED and b.score == -1
    assert b.fire(0, 0) == sea.HIT
    assert b.fire(0, 1) == sea.SUNK and b.shots[0][0] == sea.SHOT_SUNK
    assert b.fire(3, 3) == sea.WON and b.score == 29

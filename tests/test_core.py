import random
from datetime import datetime

import pytest

from games_core import days, matrix, memo, path, progression as pr, scoring, seafight_solo as sea, tower, trips
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


def msk(day: int, hour: int) -> float:
    """Время по Москве: 2026-11-<day> <hour>:00."""
    return datetime(2026, 11, day, hour, tzinfo=days.TZ).timestamp()


def test_start_minus_one_on_new_day():
    # 23:00 и 01:00 — разные сутки по Москве, хотя прошло 2 часа
    p = pr.Progress(level=8, last_success_level=8, last_played_at=msk(20, 23))
    assert pr.start_partia(p, now=msk(21, 1)) == 7
    assert p.last_success_level == 7
    # следующая партия в тот же день — без штрафа (last_played_at обновляет сохранение партии)
    p.last_played_at = msk(21, 1)
    assert pr.start_partia(p, now=msk(21, 22)) == 7


def test_start_new_day_penalty_does_not_grow_with_break():
    p = pr.Progress(level=8, last_success_level=8, last_played_at=msk(1, 12))
    assert pr.start_partia(p, now=msk(20, 12)) == 7


def test_start_same_day_no_penalty():
    p = pr.Progress(level=8, last_success_level=8, last_played_at=msk(21, 0))
    assert pr.start_partia(p, now=msk(21, 23)) == 8


def test_start_new_day_not_below_first_level():
    p = pr.Progress(level=1, last_success_level=1, last_played_at=msk(20, 12))
    assert pr.start_partia(p, now=msk(21, 12)) == 1


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
    assert rnd.numbers == [1, 2, 3] and (rnd.rows, rnd.cols) == (3, 3)


@pytest.mark.parametrize("level", range(1, 70))
def test_tower_numbers_ascending_and_fit(level):
    rng = random.Random(level)
    rnd = tower.TowerRound.generate(level, rng)
    assert rnd.numbers == sorted(set(rnd.numbers))
    assert len(rnd.cells) == len(rnd.numbers) <= rnd.rows * rnd.cols
    assert rnd.cols <= MAX_COLS and rnd.rows <= MAX_ROWS - 1


def test_tower_harder_levels():
    rng = random.Random(5)
    starts = {tower.make_numbers(3, rng)[0] for _ in range(50)}
    assert min(starts) >= 2


@pytest.mark.parametrize("level", range(1, 40))
def test_tower_gaps_from_five_numbers(level):
    """До 5 чисел — подряд; с 5 — куски подряд и gaps_count(n) разрывов между ними: 3, 4, 7, 8, 9."""
    rng = random.Random(level)
    for _ in range(20):
        numbers = tower.make_numbers(level, rng)
        steps = [b - a for a, b in zip(numbers, numbers[1:])]
        gaps = sum(1 for d in steps if d > 1)
        assert gaps == tower.gaps_count(len(numbers))
        assert (gaps > 0) == (len(numbers) >= tower.GAPS_FROM)
        assert all(1 <= d <= tower.tower_params(level)[3] for d in steps)


def test_tower_order():
    rnd = tower.TowerRound.generate(2, random.Random(3))
    by_num = {n: cell for cell, n in rnd.cells.items()}
    assert rnd.tap(*by_num[rnd.numbers[1]]) == tower.MISS
    assert rnd.tap(*by_num[rnd.numbers[0]]) == tower.HIT
    assert rnd.tap(*by_num[rnd.numbers[0]]) == tower.IGNORED
    # клетка без числа неактивна: нажатие не ошибка
    empty = next((r, c) for r in range(rnd.rows) for c in range(rnd.cols) if (r, c) not in rnd.cells)
    assert rnd.tap(*empty) == tower.IGNORED


# --- проложи дорогу ---

@pytest.mark.parametrize("level", range(1, 30))
def test_path_solvable_and_fits(level):
    for seed in range(40):
        rnd = path.PathRound.generate(level, random.Random(seed * 100 + level))
        a, b = rnd.ends
        assert path.distance(a, b) >= path.MIN_ENDS_DISTANCE
        assert rnd.blocks and not rnd.blocks & set(rnd.ends)
        assert rnd.icons[0] in path.PEOPLE and rnd.icons[1] in path.HOUSES
        assert rnd.solution and rnd.shortest >= 2
        assert rnd.cols <= MAX_COLS and rnd.rows <= MAX_ROWS - 1
        # кратчайшая дорога кладётся нажатиями и даёт CLEARED ровно на последней клетке
        results = [rnd.tap(*cell) for cell in rnd.solution]
        assert results[-1] == path.CLEARED and set(results[:-1]) <= {path.HIT}
        assert rnd.is_shortest()


@pytest.mark.parametrize("level", range(1, 46))
def test_path_route_matches_level(level):
    """Сложность дороги на уровне ровная: повороты и длина — в диапазонах уровня."""
    spec = path.path_params(level)
    misses = []
    for seed in range(50):
        rnd = path.PathRound.generate(level, random.Random(seed * 1000 + level))
        assert (rnd.rows, rnd.cols, len(rnd.blocks)) == (spec.rows, spec.cols, spec.blocks)
        misses.append(path.band_miss(rnd.turns, spec.turns) + path.band_miss(rnd.shortest, spec.length))
    assert sum(m == 0 for m in misses) >= 45 and max(misses) <= 1, misses


def test_path_field_grows_slowly_route_gets_harder():
    specs = [path.path_params(level) for level in range(1, 60)]
    for a, b in zip(specs, specs[1:]):
        assert b.rows >= a.rows and b.cols >= a.cols and b.blocks >= a.blocks
        if (b.rows, b.cols) == (a.rows, a.cols):
            # на том же поле дорога не проще
            assert b.turns[0] >= a.turns[0] and b.length[0] >= a.length[0]
    sizes = [(s.rows, s.cols) for s in specs]
    assert sizes.index((7, 7)) + 1 >= 11                   # 7×7 не раньше 11-го уровня
    assert all(sizes.count(size) >= 3 for size in set(sizes[:-1]))   # на каждом поле не меньше 3 уровней
    assert max(s.rows for s in specs) <= path.FIELD_ROWS_LIMIT


def route_turns(a, route, b) -> int:
    cells = [a, *route, b]
    steps = [(y[0] - x[0], y[1] - x[1]) for x, y in zip(cells, cells[1:])]
    return sum(s != t for s, t in zip(steps, steps[1:]))


def all_shortest_routes(rnd: path.PathRound):
    """Все кратчайшие дороги перебором (для маленьких полей)."""
    a, b = rnd.ends
    out = []

    def walk(route):
        if len(route) > rnd.shortest:
            return
        last = route[-1] if route else a
        for x in rnd.neighbors(last):
            if x == b and len(route) == rnd.shortest:
                out.append(list(route))
            elif rnd.free(x) and x not in route:
                walk(route + [x])
    walk([])
    return out


def test_path_solution_is_simplest_shortest():
    for seed in range(150):
        rnd = path.PathRound.generate(1 + seed % 6, random.Random(seed))
        a, b = rnd.ends
        routes = all_shortest_routes(rnd)
        assert rnd.solution in routes
        assert rnd.turns == route_turns(a, rnd.solution, b) == min(route_turns(a, r, b) for r in routes)


def test_path_turns_of_straight_and_bent_roads():
    straight = path.PathRound(5, 5, ((0, 0), (0, 4)), {(4, 4)})
    assert straight.solution == [(0, 1), (0, 2), (0, 3)] and straight.turns == 0
    # из угла в угол кратчайших много, самая простая — с одним поворотом
    corner = path.PathRound(5, 5, ((0, 0), (3, 3)), {(4, 4)})
    assert corner.shortest == 5 and corner.turns == 1
    # препятствие на прямой: обход по нижнему ряду — 2 поворота, а не 4 (через (1,1) и (1,3))
    detour = path.PathRound(3, 5, ((1, 0), (1, 4)), {(1, 2), (0, 2)})
    assert detour.solution == [(2, 0), (2, 1), (2, 2), (2, 3), (2, 4)] and detour.turns == 2


def straight_round() -> path.PathRound:
    """Поле 5×5: человек (0,0), дом (0,4), препятствие (1,2). Кратчайшая дорога — (0,1),(0,2),(0,3)."""
    return path.PathRound(5, 5, ((0, 0), (0, 4)), {(1, 2)})


def test_path_any_order():
    rnd = straight_round()
    assert rnd.shortest == 3
    # с середины, потом к краям
    assert [rnd.tap(*x) for x in ((0, 2), (0, 3), (0, 1))] == [path.HIT, path.HIT, path.CLEARED]
    assert rnd.length() == 3 and rnd.is_shortest()
    # клетки вдали от концов и не по соседству друг с другом — не ошибка
    rnd = straight_round()
    assert [rnd.tap(*x) for x in ((4, 4), (2, 0), (0, 2))] == [path.HIT] * 3


def test_path_detour_and_extra_cells_are_not_shortest():
    rnd = straight_round()
    route = [(1, 0), (2, 0), (2, 1), (2, 2), (2, 3), (2, 4), (1, 4)]    # в обход препятствия
    assert [rnd.tap(*x) for x in route] == [path.HIT] * 6 + [path.CLEARED]
    assert rnd.length() == 7 and not rnd.is_shortest()
    rnd = straight_round()
    assert [rnd.tap(*x) for x in ((4, 4), (0, 1), (0, 2), (0, 3))] == [path.HIT] * 3 + [path.CLEARED]
    assert not rnd.is_shortest()


def test_path_taps_that_do_nothing_and_block():
    rnd = straight_round()
    assert rnd.tap(0, 1) == path.HIT and rnd.tap(0, 1) == path.IGNORED         # уже на дороге
    assert rnd.tap(5, 0) == path.IGNORED                                       # вне поля
    assert rnd.tap(1, 2) == path.MISS                                          # препятствие
    assert rnd.road == [(0, 1)]


def test_path_ends_tap_like_road_but_do_not_count():
    """Человек и дом нажимаются как обычная клетка — иначе их можно найти вслепую."""
    rnd = straight_round()
    assert rnd.tap(0, 0) == path.HIT and rnd.tap(0, 4) == path.HIT
    assert rnd.tap(0, 0) == path.IGNORED
    assert rnd.marked == {(0, 0), (0, 4)} and rnd.road == []
    assert [rnd.tap(*x) for x in ((0, 1), (0, 2), (0, 3))] == [path.HIT, path.HIT, path.CLEARED]
    assert rnd.length() == 3 and rnd.is_shortest()


def test_moscow_days():
    ts = 1_000_000.0                                   # 1970-01-12 16:46:40 по Москве
    assert days.day_key(ts) == "1970-01-12" and days.hour(ts) == 16
    assert days.local(days.day_start(ts)).hour == 0
    noon = days.next_time(ts, 12, 0)
    assert days.day_key(noon) == "1970-01-13" and days.hour(noon) == 12
    assert days.next_time(ts, 19, 0) - ts < 3 * 3600


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


def test_memo_moves_limit():
    assert memo.moves_limit(3) == 6
    assert memo.MemoBoard.generate(1, random.Random(0)).moves_limit == 6


def test_level_up_carries_to_next_partia():
    p = pr.Progress(level=1, last_success_level=1, last_played_at=0.0)
    for _ in range(pr.WINS_TO_LEVEL_UP):
        pr.register_win(p)
    assert p.level == 2 and pr.start_partia(p, now=60.0) == 2


def test_level_down_carries_to_next_partia():
    p = pr.Progress(level=5, last_success_level=5, last_played_at=0.0)
    pr.register_fail(p)
    pr.register_fail(p)
    assert pr.start_partia(p, now=60.0) == 4


def test_single_win_level_up():
    p = pr.Progress(level=3, last_success_level=3)
    assert pr.register_win(p, wins_needed=1) == 1 and p.level == 4


# --- поездка на числах ---

def test_road_weight():
    """Партия без ошибок: на 1-м уровне — 60% дороги, с 15-го — вся; доля растёт с уровнем."""
    weights = [trips.road_weight(level) for level in range(1, 30)]
    assert weights[0] == 0.6 and trips.road_weight(trips.FULL_ROAD_LEVEL) == 1.0 and weights[-1] == 1.0
    assert weights == sorted(weights)


def test_trip_lines():
    assert "не завелась" in trips.trip_lines(0)[0]
    almost = trips.trip_lines(10)
    assert "10 км" in almost[0] and "Ещё 6 км" in almost[1]
    cheer, place = trips.trip_lines(270)
    assert "Отличная поездка" in cheer and "270 км" in cheer and "до Ярославля — 265 км" in place
    assert "Владивостока — 9200 км" in trips.trip_lines(9300)[1]
    assert "по экватору" in trips.trip_lines(10 ** 6)[1]
    assert [d for d, _ in trips.TRIPS] == sorted(d for d, _ in trips.TRIPS)

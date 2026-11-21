"""Компьютер в морском бое: не подглядывает, стреляет только в новые клетки, «продвинутый» сильнее."""
import inspect
import random
import statistics
import time

import pytest

from games_core import sea_ai
from games_core import seafight_mp as mp
from games_core import seafight_solo as sea
from tests.harness import World, mp_game, wait_ai


def play(strategy, ship_set: str, seed: int) -> int:
    """Сколько выстрелов стратегии нужно, чтобы потопить случайную расстановку."""
    rng = random.Random(seed)
    board = sea.SeaBoard(sea.generate_ships(sea.SHIP_SETS[ship_set], rng))
    sizes = sea.SHIP_SETS[ship_set]
    for n in range(1, board.rows * board.cols + 1):
        r, c = strategy([row[:] for row in board.shots], sizes, rng)
        result = board.fire(r, c)
        assert result != sea.IGNORED, f"выстрел в уже обстрелянную клетку {(r, c)}"
        if result == sea.WON:
            return n
    raise AssertionError("корабли так и не потоплены")


def baseline(shots, sizes, rng):
    """Опорная стратегия: охота по шахматной раскраске и добивание вдоль линии, мимо ореолов."""
    view = sea_ai.View(shots, sizes)
    careful = [cell for cell in view.unknown if cell not in view.empty] or view.unknown
    if view.hits:
        targets = view._next_to_hits(careful, sloppy=False)
        if targets:
            return rng.choice(targets)
    even = [cell for cell in careful if sum(cell) % 2 == 0] or careful
    return rng.choice(even)


def level(name):
    return lambda shots, sizes, rng: sea_ai.choose_shot(shots, sizes, name, rng)


@pytest.fixture
def fixed_samples(monkeypatch):
    """Ровно SAMPLE_MIN расстановок на ход, без настоящих часов: результат не зависит от скорости машины."""
    monkeypatch.setattr(sea_ai, "SAMPLE_SECONDS", 0.0)


def test_input_is_only_own_shots():
    """В choose_shot нет ничего, кроме сетки своих выстрелов, набора, уровня и случайности."""
    assert list(inspect.signature(sea_ai.choose_shot).parameters) == ["shots", "sizes", "level", "rng"]


async def test_game_passes_only_ai_shots(monkeypatch):
    """В партии компьютеру уходит копия его сетки выстрелов — ни кораблей соперника, ни партии."""
    seen = []
    real = sea_ai.choose_shot

    def spy(*args):
        seen.append(args)
        return real(*args)
    monkeypatch.setattr(sea_ai, "choose_shot", spy)
    world = World()
    try:
        chat = world.chat()
        await chat.send("ain:advanced:0:reduced:auto")
        game = mp_game(chat)
        human_ships = {cell for ship in game.host.ships for cell in ship}
        for _ in range(3):
            free = next((r, c) for r in range(sea.ROWS) for c in range(sea.COLS)
                        if game.host.shots[r][c] == sea.UNKNOWN)
            await chat.tap(*free)
            before = [row[:] for row in game.guest.shots]
            await wait_ai(world, chat)
            shots, sizes, lvl, rng = seen[-1]
            assert shots == before and shots is not game.guest.shots
            assert sizes == sea.SHIP_SETS["reduced"] and lvl == "advanced"
            assert not any(isinstance(x, (mp.MpGame, mp.Side)) for x in seen[-1])
            assert {(r, c) for r in range(sea.ROWS) for c in range(sea.COLS)
                    if shots[r][c] in (sea.SHOT_HIT, sea.SHOT_SUNK)} <= human_ships
    finally:
        await world.close()
    assert len(seen) == 3


@pytest.mark.parametrize("name", sea_ai.LEVELS)
@pytest.mark.parametrize("ship_set", sorted(sea.SHIP_SETS))
def test_same_view_same_shot(name, ship_set, fixed_samples):
    """Ход зависит только от увиденного: при тех же выстрелах и seed — та же клетка."""
    rng = random.Random(7)
    board = sea.SeaBoard(sea.generate_ships(sea.SHIP_SETS[ship_set], rng))
    for _ in range(12):
        board.fire(*sea_ai.choose_shot(board.shots, sea.SHIP_SETS[ship_set], name, rng))
    shots = [row[:] for row in board.shots]
    picks = {sea_ai.choose_shot(shots, sea.SHIP_SETS[ship_set], name, random.Random(3)) for _ in range(3)}
    assert len(picks) == 1


@pytest.mark.parametrize("name", sea_ai.LEVELS)
@pytest.mark.parametrize("ship_set", sorted(sea.SHIP_SETS))
def test_games_finish_without_repeated_shots(name, ship_set, fixed_samples):
    for seed in range(3):
        assert play(level(name), ship_set, seed) <= sea.ROWS * sea.COLS


def test_advanced_avoids_cells_known_to_be_empty(fixed_samples):
    """Вокруг потопленного корабля и по углам раненой клетки кораблей быть не может."""
    for seed in range(4):
        rng = random.Random(seed)
        sizes = sea.SHIP_SETS["full"]
        board = sea.SeaBoard(sea.generate_ships(sizes, rng))
        while not board.is_won():
            view = sea_ai.View(board.shots, sizes)
            cell = sea_ai.choose_shot(board.shots, sizes, sea_ai.ADVANCED, rng)
            if any(c not in view.empty for c in view.unknown):
                assert cell not in view.empty, f"seed {seed}: выстрел в заведомо пустую {cell}"
            board.fire(*cell)


def test_wounded_ship_is_longer_than_its_hits(fixed_samples):
    """Раненая клетка — не однопалубный корабль (его бы уже потопило): малый набор добивается рядом.
    (В плотном полном наборе угол бывает вероятнее соседа раненой — тогда бьёт туда.)"""
    shots = [[sea.UNKNOWN] * sea.COLS for _ in range(sea.ROWS)]
    shots[3][3] = sea.SHOT_HIT
    for seed in range(5):
        r, c = sea_ai.choose_shot(shots, sea.SHIP_SETS["reduced"], sea_ai.ADVANCED, random.Random(seed))
        assert abs(r - 3) + abs(c - 3) == 1
    # два раненых в ряд — третья клетка по линии, если корабль на 3 ещё не потоплен
    shots[3][4] = sea.SHOT_HIT
    space = sea_ai.Space(sea_ai.View(shots, [3]))
    weights = space.exact(10 ** 6)
    assert set(weights) - {(3, 3), (3, 4)} == {(3, 2), (3, 5)}


def test_sampling_matches_exact_count():
    """Сэмплирование оценивает те же вероятности, что и полный перебор."""
    shots = [[sea.UNKNOWN] * sea.COLS for _ in range(sea.ROWS)]
    for r, c in [(0, 0), (1, 3), (2, 5), (4, 1), (5, 4), (6, 6), (3, 3)]:
        shots[r][c] = sea.SHOT_MISS
    shots[4][4] = sea.SHOT_HIT
    space = sea_ai.Space(sea_ai.View(shots, [3, 2, 1]))
    exact, sampled = space.exact(10 ** 7), space.sampled(random.Random(1))
    tx, ts = sum(exact.values()), sum(sampled.values())
    assert max(abs(exact[cell] / tx - sampled.get(cell, 0) / ts) for cell in exact) < 0.01


def test_exact_gives_up_over_budget():
    shots = [[sea.UNKNOWN] * sea.COLS for _ in range(sea.ROWS)]
    assert sea_ai.Space(sea_ai.View(shots, sea.SHIP_SETS["full"])).exact(1000) is None


@pytest.mark.parametrize("ship_set", sorted(sea.SHIP_SETS))
def test_move_fits_time_budget(ship_set):
    """Самый тяжёлый ход — первый: расстановок больше всего. Укладываемся в бюджет с запасом."""
    shots = [[sea.UNKNOWN] * sea.COLS for _ in range(sea.ROWS)]
    started = time.perf_counter()
    sea_ai.choose_shot(shots, sea.SHIP_SETS[ship_set], sea_ai.ADVANCED, random.Random(1))
    assert time.perf_counter() - started < sea_ai.SAMPLE_SECONDS + 0.5


def test_levels_differ_in_strength(fixed_samples):
    """Полный набор, одни и те же расстановки: «продвинутый» топит быстрее опорной стратегии,
    «обычный» — медленнее неё. Замер на 80 партиях: 26.5 / 31.9 / 34.5 выстрела."""
    seeds = range(12)
    advanced = statistics.mean(play(level(sea_ai.ADVANCED), "full", s) for s in seeds)
    base = statistics.mean(play(baseline, "full", s) for s in seeds)
    normal = statistics.mean(play(level(sea_ai.NORMAL), "full", s) for s in seeds)
    assert advanced < base - 2 < normal - 2, (advanced, base, normal)

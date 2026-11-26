"""«⚓ Кораблики» (docs/boats/tz.md §6.4): генератор, расписание, судья, открытие уровней, нажатия, мотивация.

Образцы судьи docs/boats/fixtures/judge-*.json — для judge.ts клиента; обновить тем же коммитом, что и формулу:
    UPDATE_FIXTURES=1 .venv/bin/python -m pytest tests/test_boats.py
"""
import json
import os
import random
import time
from pathlib import Path

import pytest

from games_core import boats as B
from games_core import motivation
from games_core.motivation import Partia, replay
from games_core.sessions import Player
from games_core.storage import Storage
from tests.harness import World, live, play_boats

FIXTURES = Path(__file__).resolve().parent.parent / "docs" / "boats" / "fixtures"
SEEDS = 300


# --- генератор ---

def check_field(f: B.Field) -> None:
    n, cols, rows = B.LEVELS[f.level][:3]
    assert (f.rows, f.cols) == (rows, cols)
    cells = set(f.parent)
    assert all(0 <= r < rows and 0 <= c < cols for r, c in cells), "клетка за полем"
    # дерево с корнем в бухте: каждая клетка достижима, потомки — соседи, связи согласованы
    assert f.parent[f.bay] is None and set(f.dist) == cells
    for x, kids in f.children.items():
        for y in kids:
            assert f.parent[y] == x and abs(x[0] - y[0]) + abs(x[1] - y[1]) == 1
    for x, p in f.parent.items():
        if p is not None:
            assert x in f.children[p]
    # пути не пересекаются: стороны клетки (вход и выходы) разные
    for x in cells:
        sides = ([B.side(x, f.parent[x])] if f.parent[x] else []) + [B.side(x, y) for y in f.children[x]]
        assert len(sides) == len(set(sides))
    # бухта на краю, канал из неё — внутрь поля
    br, bc = f.bay
    assert br in (0, rows - 1) or bc in (0, cols - 1)
    assert len(f.children[f.bay]) == 1
    piers = [x for x in cells if not f.children[x] and x != f.bay]
    switches = [x for x in cells if len(f.children[x]) == 2]
    assert sorted(piers) == f.piers and len(piers) == n
    assert sorted(switches) == f.switches and len(switches) == n - 1
    first = f.children[f.bay][0]
    assert len(f.children[first]) == 1, "до первой развилки меньше 2 клеток"
    assert max(f.switches_on_way(x) for x in piers) <= B.max_switches(n)
    assert sorted(f.colors.values()) == list(range(n)), "цвета причалов не 0…N−1"
    assert all(v in (0, 1) for v in f.init.values())
    # выходы развилки — по часовой стрелке от стороны после входа
    for x in switches:
        order = B.clockwise_after(B.side(x, f.parent[x]))
        outs = [B.side(x, y) for y in f.children[x]]
        assert outs == sorted(outs, key=order.index)


@pytest.mark.parametrize("level", sorted(B.LEVELS))
def test_generator_invariants(level):
    times = []
    for seed in range(SEEDS):
        t0 = time.perf_counter()
        f = B.generate(level, f"s{seed}")
        times.append(time.perf_counter() - t0)
        check_field(f)
    times.sort()
    assert times[int(len(times) * 0.99)] < 0.1, "99-й перцентиль времени генерации ≥ 100 мс"


def test_generator_deterministic():
    for level in (1, 8, 15):
        a, b = B.generate(level, "abc"), B.generate(level, "abc")
        assert (a.bay, a.parent, a.children, a.colors, a.init) == (b.bay, b.parent, b.children, b.colors, b.init)
        assert B.schedule(level, "abc") == B.schedule(level, "abc")
    assert B.generate(15, "abc").cells() != B.generate(15, "abd").cells()


def test_generator_gives_up_to_another_seed(monkeypatch):
    calls = []

    def fail_first(level, rng):
        calls.append(1)
        if len(calls) <= B.MAX_TRIES:
            raise B._Fail
        return real(level, rng)
    real = B._try_generate
    monkeypatch.setattr(B, "_try_generate", fail_first)
    check_field(B.generate(3, "x"))


# --- расписание ---

def expected_times(level, game_ms=B.GAME_MS):
    _, _, _, g, a, p = B.LEVELS[level]
    out, t = [], B.FIRST_BOAT_MS
    while t < game_ms:
        out.append(t)
        t += p if len(out) % g == 0 else a
    return out


def test_schedule_times():
    assert [b.t for b in B.schedule(1, "x")][:4] == [500, 6500, 12500, 18500]
    assert [b.t for b in B.schedule(7, "x")][:7] == [500, 3100, 5700, 13100, 15700, 18300, 25700]
    assert [b.t for b in B.schedule(15, "x")][:9] == [500, 2100, 3700, 5300, 10100, 11700, 13300, 14900, 19700]
    counts = {1: 20, 2: 21, 3: 23, 4: 24, 5: 26, 6: 27, 7: 30, 8: 32, 9: 34, 10: 37, 11: 39, 12: 42,
              13: 45, 14: 48, 15: 51}
    for level, n in counts.items():
        sched = B.schedule(level, "y")
        assert [b.t for b in sched] == expected_times(level)
        assert len(sched) == n, level
        assert [b.id for b in sched] == list(range(n))


def test_schedule_colors():
    for level in B.LEVELS:
        for seed in range(30):
            colors = [b.color for b in B.schedule(level, str(seed))]
            n = B.LEVELS[level][0]
            assert all(0 <= c < n for c in colors)
            assert not any(colors[i] == colors[i + 1] == colors[i + 2] for i in range(len(colors) - 2))


def test_average_interval_falls_smoothly():
    avg = [(a * (g - 1) + p) / g for _, _, _, g, a, p in (B.LEVELS[L] for L in sorted(B.LEVELS))]
    assert all(x > y for x, y in zip(avg, avg[1:]))
    assert avg[0] == 6000 and avg[-1] == 2400


# --- судья ---

def tick_sim(f, sched, toggles, game_ms=B.GAME_MS, tick=1):
    """Покадровая симуляция для сверки: выход развилки фиксируется в момент входа кораблика в её клетку."""
    state = dict(f.init)
    tog = sorted(toggles)
    ti = si = 0
    active, out = [], []
    for now in range(0, game_ms + 1, tick):
        while ti < len(tog) and tog[ti][0] <= now:
            x = (tog[ti][1], tog[ti][2])
            if x in state:
                state[x] ^= 1
            ti += 1
        while si < len(sched) and sched[si].t <= now:
            active.append({"b": sched[si], "cell": f.bay, "exit": None})
            si += 1
        for a in list(active):
            while True:
                x, b = a["cell"], a["b"]
                ch = f.children[x]
                if not ch:
                    t_arr = b.t + f.dist[x] * B.MS_PER_CELL
                    if now >= t_arr:
                        out.append((t_arr, b.id, x[0], x[1], f.colors[x] == b.color))
                        active.remove(a)
                    break
                if now < b.t + (2 * f.dist[x] + 1) * B.MS_PER_CELL // 2:
                    break
                y = ch[0] if len(ch) == 1 else ch[a["exit"]]
                a["cell"] = y
                a["exit"] = state[y] if len(f.children[y]) == 2 else None
    return sorted(out)


def random_toggles(f, rng, k=80, game_ms=B.GAME_MS):
    sws = f.switches
    return sorted((rng.randrange(game_ms), *rng.choice(sws)) for _ in range(k))


def at_enter_toggles(f, sched, rng):
    """Переключения ровно в момент входа кораблика в развилку и на 1 мс раньше/позже."""
    out = []
    for b in sched[::2]:
        x = f.bay
        while f.children[x]:
            ch = f.children[x]
            if len(ch) == 2:
                t = B.enter_ms(f, b.t, x) + rng.choice((-1, 0, 0, 1))
                if t >= 0:
                    out.append((t, *x))
                x = ch[rng.randint(0, 1)]
            else:
                x = ch[0]
    return sorted(out)


@pytest.mark.parametrize("level", [1, 6, 12, 15])
def test_judge_matches_tick_simulation(level):
    rng = random.Random(level)
    f = B.generate(level, f"j{level}")
    sched = B.schedule(level, f"j{level}")
    for toggles in (random_toggles(f, rng), B.perfect_toggles(f, sched), at_enter_toggles(f, sched, rng)):
        assert B.judge(f, sched, toggles) == tick_sim(f, sched, toggles)


def test_judge_ignores_non_switch_and_counts_until_end():
    f = B.generate(3, "q")
    sched = B.schedule(3, "q")
    plan = B.perfect_toggles(f, sched)
    noise = [(t, r, c) for t, (r, c) in zip(range(100, 9000, 500), f.piers + [f.bay] * 20)]
    assert B.judge(f, sched, sorted(plan + noise)) == B.judge(f, sched, plan)
    done = B.judge(f, sched, plan)
    assert all(a[0] <= B.GAME_MS for a in done) and len(done) < len(sched)
    short = B.judge(f, sched, plan, game_ms=60_000)
    assert short == [a for a in done if a[0] <= 60_000]


@pytest.mark.parametrize("level", sorted(B.LEVELS))
def test_perfect_player_scores_100(level):
    for seed in range(4):
        f, sched = B.generate(level, f"p{seed}"), B.schedule(level, f"p{seed}")
        plan = B.perfect_toggles(f, sched)
        done = B.judge(f, sched, plan)
        assert done and all(a[4] for a in done), (level, seed)
        assert all(0 <= t <= B.GAME_MS for t, _, _ in plan)


def test_points_use_streak_multipliers():
    arr = [(1, i, 0, 0, True) for i in range(6)] + [(2, 6, 0, 0, False), (3, 7, 0, 0, True)]
    score, streak = B.points(2, arr)
    assert score == 20 * 5 + 30 + 20 and streak == 1


# --- образцы судьи для клиента ---

def fixture_case(level, seed, toggles_kind):
    f, sched = B.generate(level, seed), B.schedule(level, seed)
    rng = random.Random(seed)
    if toggles_kind == "perfect":
        toggles = B.perfect_toggles(f, sched)
    elif toggles_kind == "enter":
        toggles = at_enter_toggles(f, sched, rng)
    else:
        toggles = random_toggles(f, rng, 60)
    arrivals = B.judge(f, sched, toggles)
    assert arrivals == tick_sim(f, sched, toggles)
    return {
        "level": level, "ms_per_cell": B.MS_PER_CELL, "game_ms": B.GAME_MS,
        "grid": {"rows": f.rows, "cols": f.cols}, "cells": f.cells(),
        "boats": [{"id": b.id, "t": b.t, "color": b.color} for b in sched],
        "toggles": [list(x) for x in toggles],
        "arrivals": [[t, i, r, c, ok] for t, i, r, c, ok in arrivals],
    }


FIXTURE_CASES = {
    "judge-level1": (1, "fx1", "random"),
    "judge-level6": (6, "fx6", "random"),
    "judge-level12": (12, "fx12", "perfect"),
    "judge-level15": (15, "fx15", "random"),
    "judge-at-enter": (8, "fx8", "enter"),
}


def test_judge_fixtures_match_code():
    update = os.getenv("UPDATE_FIXTURES") == "1"
    stale = []
    for name, case in FIXTURE_CASES.items():
        text = json.dumps(fixture_case(*case), ensure_ascii=False, separators=(",", ":")) + "\n"
        path = FIXTURES / f"{name}.json"
        if update:
            FIXTURES.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
        elif not path.exists() or path.read_text(encoding="utf-8") != text:
            stale.append(name)
    assert not stale, f"образцы судьи устарели: {stale} — UPDATE_FIXTURES=1 .venv/bin/python -m pytest {__file__}"


# --- партия: открытие уровней, нажатия, «Закончить» ---

def session(storage, level=1, clock=lambda: 1000.0, rng=None, uid=7):
    player = Player("tg", uid, "Тестер", uid, web=True)
    return B.BoatsSession("abc123", player, storage, rng or random.Random(1), clock, level=level)


def fake_arrivals(correct, arrived):
    return [(1000 + i, i, 0, 0, i < correct) for i in range(arrived)]


@pytest.mark.parametrize("correct, arrived, opens", [(9, 10, True), (18, 20, True), (89, 100, False),
                                                       (17, 19, False), (9, 9, False), (0, 0, False)])
def test_unlock_threshold(correct, arrived, opens):
    assert B.unlocks(correct, arrived) is opens
    storage = Storage(":memory:")
    s = session(storage)
    s.arrivals = lambda until=None: fake_arrivals(correct, arrived)
    s.begin_play()
    s.finish()
    assert storage.load_progress("tg", 7, "boats").level == (2 if opens else 1)
    assert s.unlocked is opens


def test_replay_of_lower_level_keeps_opened_and_no_downgrade():
    storage = Storage(":memory:")
    p = storage.load_progress("tg", 7, "boats")
    p.level = p.last_success_level = 5
    storage.save_result("tg", 7, "boats", p, None, 1000.0)
    for level, (correct, arrived) in ((3, (20, 20)), (5, (0, 20)), (4, (19, 20))):
        s = session(storage, level)
        s.arrivals = lambda until=None, ca=(correct, arrived): fake_arrivals(*ca)
        s.finish()
        assert storage.load_progress("tg", 7, "boats").level == 5, level
    # в другой день уровень тот же: штрафа за новый день нет
    s = session(storage, 5, clock=lambda: 1000.0 + 5 * 86400)
    assert s.level == 5 and s.progress.level == 5
    assert storage.boats_best("tg", 7) == {3: (20, 20), 5: (0, 20), 4: (19, 20)}


def test_level_15_does_not_open_16():
    storage = Storage(":memory:")
    p = storage.load_progress("tg", 7, "boats")
    p.level = 15
    storage.save_result("tg", 7, "boats", p, None, 1000.0)
    s = session(storage, 15)
    s.arrivals = lambda until=None: fake_arrivals(40, 40)
    s.finish()
    assert storage.load_progress("tg", 7, "boats").level == 15 and not s.unlocked


def test_best_result_prefers_more_correct_then_accuracy():
    storage = Storage(":memory:")
    p = storage.load_progress("tg", 7, "boats")
    for correct, arrived in ((10, 20), (12, 30), (12, 13), (11, 11)):
        storage.save_boats("tg", 7, p, correct, 1, correct, arrived, 1000.0)
    assert storage.boats_best("tg", 7) == {1: (12, 13)}


def test_toggle_checks():
    now = [1000.0]
    storage = Storage(":memory:")
    s = session(storage, 6, clock=lambda: now[0])
    sw = s.field.switches[0]
    pier = s.field.piers[0]
    assert not s.toggle(*sw, "0"), "в отсчёте нажатия не принимаются"
    s.begin_play()
    now[0] += 10.0                                       # t_srv = 10 000
    assert not s.toggle(*pier, "10000"), "не развилка"
    assert not s.toggle(*sw, "10000.5") and not s.toggle(*sw, "abc"), "нецелое время"
    assert s.toggle(*sw, "9000")                         # в допуске — время клиента
    assert s.toggle(*sw, "12000") is True                # в допуске (1500 мс нет: 2000) — время сервера
    assert s.toggles == [(9000, *sw), (10000, *sw)]
    assert s.toggle(*sw, "9500")                         # журнал не убывает
    assert s.toggles[-1] == (10000, *sw)
    assert s.toggle(*sw, None) and s.toggles[-1][0] == 10000
    now[0] = s.play_started_at + 120.5                   # время вышло, ждём запоздавшие
    assert s.toggle(*sw, "119800"), "запоздавшее нажатие до конца партии"
    assert not s.toggle(*sw, "120700"), "после конца партии"
    assert not s.toggle(*sw, "999999")                   # не в допуске, t_srv > GAME_MS


async def test_quit_writes_nothing():
    world = World(platform="tg")
    chat = world.chat(5, "Тестер")
    try:
        await chat.open_app()
        await chat.click("Кораблики")
        await chat.click("▶ 1")
        s = live(chat)
        await play_boats(world, chat, B.perfect_toggles(s.field, s.boats)[:4], until_end=False)
        await chat.click("Закончить")
        assert s.finished and s.result is None
        await world.time.advance(200)
        for table in ("scores", "progress", "boats_results"):
            assert world.storage.conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] == 0, table
        assert motivation.journey(world.storage, "tg", 5).steps == 0
        assert "Выберите уровень" in chat.text
    finally:
        await world.close()


async def test_leaving_to_menu_mid_game_writes_nothing_but_after_time_writes():
    world = World(platform="tg")
    chat = world.chat(5, "Тестер")
    try:
        await chat.open_app()
        await chat.press("new:boats:1")
        await world.time.advance(50)
        await chat.press("menu")
        assert world.scores_count() == 0
        await chat.press("new:boats:1")
        s = live(chat)
        await world.time.advance(3 + 120.2)             # время вышло, итог ещё не посчитан (запас 1,5 с)
        assert not s.finished
        await chat.press("menu")
        assert s.finished and s.result is not None and world.scores_count() == 1
    finally:
        await world.close()


async def test_locked_and_wrong_levels():
    world = World(platform="tg")
    chat = world.chat(5, "Тестер")
    try:
        await chat.open_app()
        await chat.press("new:boats:3")
        assert "Выберите уровень" in chat.text and "уровень 2 на 90%" in chat.note and live(chat) is None
        await chat.press("new:boats:99")
        assert "Выберите уровень" in chat.text and live(chat) is None
        await chat.press("bl:4")
        assert "уровень 3" in chat.note
    finally:
        await world.close()


async def test_reconnect_frame_has_journal_and_current_state():
    world = World(platform="tg")
    chat = world.chat(5, "Тестер")
    try:
        p = world.storage.load_progress("tg", 5, "boats")
        p.level = 6
        world.storage.save_result("tg", 5, "boats", p, None, world.time.now)
        await chat.open_app()
        await chat.press("new:boats:6")
        s = live(chat)
        plan = B.perfect_toggles(s.field, s.boats)[:6]
        await play_boats(world, chat, plan, until_end=False)
        await chat.open_app()
        v = chat.screen.view
        assert v["phase"] == "play" and v["toggles"] == [list(x) for x in plan]
        assert v["clock"]["elapsed_ms"] == s.elapsed_ms()
        state = {(x["r"], x["c"]): (x["state"], x["init"]) for x in v["cells"] if x["k"] == "switch"}
        for (r, c), (now, init) in state.items():
            flips = sum(1 for _, rr, cc in plan if (rr, cc) == (r, c))
            assert now == (init + flips) % 2 and init == s.field.init[(r, c)]
        tally = v["tally"]
        done = B.judge(s.field, s.boats, s.toggles)
        assert tally["arrived"] == sum(1 for a in done if a[0] <= s.elapsed_ms())
    finally:
        await world.close()


async def test_boats_game_ms_override():
    world = World(platform="tg")
    world.mgr.boats_game_ms = 20_000
    chat = world.chat(5, "Тестер")
    try:
        await chat.open_app()
        await chat.press("new:boats:1")
        s = live(chat)
        assert s.game_ms == 20_000 and all(b.t < 20_000 for b in s.boats)
        await play_boats(world, chat)
        assert s.finished and "Партия окончена" in chat.text
    finally:
        await world.close()


# --- мотивация ---

def test_all_categories_bonus_without_multitask():
    day = 100 * 86400.0
    core = [Partia(g, 1, day + i) for i, g in enumerate(("memo", "tower", "path", "ai_full"))]
    assert replay(core).all_categories_days == 1
    assert replay(core + [Partia("boats", 1, day + 10)]).all_categories_days == 1
    assert replay([Partia("boats", 1, day)] + core).all_categories_days == 1
    assert replay(core[:3] + [Partia("boats", 1, day + 10)]).all_categories_days == 0
    assert "multitask" in motivation.CATEGORY_TITLES and motivation.CATEGORIES["boats"] == "multitask"


def test_weakest_category_never_multitask():
    p = motivation.Period(partias=8, by_category={"memory": 2, "numbers": 2, "space": 2, "logic": 2})
    assert motivation.weakest_category(p) != motivation.CATEGORY_TITLES["multitask"]
    p = motivation.Period(partias=3, by_category={"multitask": 3})
    assert motivation.weakest_category(p) == motivation.CATEGORY_TITLES["memory"]


def test_boats_not_in_daily_training():
    assert all("boats" not in games for games in motivation.DAILY_GAMES.values())


def test_history_level_is_highest_opened():
    storage = Storage(":memory:")
    s = session(storage, 1)
    s.arrivals = lambda until=None: fake_arrivals(10, 10)
    s.finish()
    assert storage.partias("tg", 7)[-1] == Partia("boats", 2, 1000.0)
    assert storage.conn.execute("SELECT level FROM scores").fetchone()[0] == 1


async def test_dbg_opens_boats_levels():
    world = World(platform="tg", debug_users={5})
    chat = world.chat(5, "Тестер")
    try:
        await chat.open_app()
        await chat.press("dbg:level:boats:7")
        assert "уровень 7" in chat.text
        await chat.press("new:boats")
        labels = [b.text for row in chat.screen.rows for b in row]
        assert "▶ 7" in labels and "6" in labels and "🔒 8" in labels
        await chat.press("dbg:level:boats:16")
        assert "Не понял" in chat.text
    finally:
        await world.close()

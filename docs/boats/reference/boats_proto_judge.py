"""Образец судьи, расписания группами, покадровой сверки и идеального игрока (прототип, НЕ для продакшена).

Запуск: python3 boats_proto_judge.py — сверка судьи с покадровой симуляцией (шаг 1 мс) и проверка идеального игрока.
См. docs/boats/tz.md §3.2, §5.3.
"""
import sys, random
sys.path.insert(0, ".")
import boats_proto_gen as gen2
from boats_proto_gen import side

MS_PER_CELL = 2000
GAME_MS = 120000
FIRST_MS = 500
# уровень -> (корабликов в группе, интервал внутри группы мс, пауза после группы мс)
WAVES = {1: (1, 0, 6000), 2: (1, 0, 5700), 3: (2, 3400, 7400), 4: (2, 3200, 7000),
         5: (2, 3000, 6600), 6: (2, 2800, 6200), 7: (3, 2600, 7400), 8: (3, 2400, 6900),
         9: (3, 2200, 6400), 10: (3, 2000, 5900), 11: (3, 1900, 5500), 12: (4, 1800, 6200),
         13: (4, 1700, 5700), 14: (4, 1600, 5400), 15: (4, 1600, 4800)}

def schedule(g, L, rng):
    size, inner, pause = WAVES[L]
    t = FIRST_MS; out = []; k = 0
    while t < GAME_MS:
        c = rng.randrange(g["n"])
        while len(out) >= 2 and out[-1][1] == c and out[-2][1] == c:
            c = rng.randrange(g["n"])
        out.append((t, c))
        k += 1
        t += pause if k % size == 0 else inner
    return out

def tree_info(g):
    """dist (клеток от центра входа), для развилок — дети [a,b] по порядку."""
    dist = {g["src"]: 0}
    order = [g["src"]]
    for x in order:
        for y in g["children"][x]:
            dist[y] = dist[x] + 1
            order.append(y)
    return dist

def judge(g, sched, color_of_station, init_state, toggles):
    """toggles: список (t_ms, switch_cell). Возвращает [(t_arrive, color, station, ok)]."""
    dist = tree_info(g)
    by_sw = {}
    for t, sw in sorted(toggles):
        by_sw.setdefault(sw, []).append(t)
    res = []
    for t0, col in sched:
        x = g["src"]
        while g["children"][x]:
            ch = g["children"][x]
            if len(ch) == 1:
                x = ch[0]; continue
            t_enter = t0 + (2 * dist[x] - 1) * MS_PER_CELL // 2
            flips = sum(1 for t in by_sw.get(x, []) if t <= t_enter)
            x = ch[(init_state[x] + flips) % 2]
        t_arr = t0 + dist[x] * MS_PER_CELL
        if t_arr <= GAME_MS:
            res.append((t_arr, col, x, color_of_station[x] == col))
    return sorted(res)

def tick_sim(g, sched, color_of_station, init_state, toggles, tick=1):
    """Покадровая симуляция для сверки: выход развилки фиксируется в момент входа в её клетку."""
    state = dict(init_state)
    tog = sorted(toggles); ti = 0
    dist = tree_info(g)
    res = []; si = 0; active = []
    for now in range(0, GAME_MS + 1, tick):
        while ti < len(tog) and tog[ti][0] <= now:
            state[tog[ti][1]] ^= 1; ti += 1
        while si < len(sched) and sched[si][0] <= now:
            active.append({"t0": sched[si][0], "col": sched[si][1], "cell": g["src"], "exit": None}); si += 1
        for b in list(active):
            while True:
                x = b["cell"]; ch = g["children"][x]
                if not ch:
                    if now >= b["t0"] + dist[x] * MS_PER_CELL:
                        res.append((b["t0"] + dist[x] * MS_PER_CELL, b["col"], x, color_of_station[x] == b["col"]))
                        active.remove(b)
                    break
                boundary = b["t0"] + (2 * dist[x] + 1) * MS_PER_CELL // 2
                if now < boundary:
                    break
                y = ch[0] if len(ch) == 1 else ch[b["exit"]]
                b["cell"] = y
                b["exit"] = state[y] if len(g["children"][y]) == 2 else None
    return sorted(res)

def perfect_toggles(g, sched, color_of_station, init_state):
    """Идеальный игрок: перед входом каждого кораблика в развилку ставит её как надо (за 300 мс)."""
    dist = tree_info(g)
    target = {v: k for k, v in color_of_station.items()}
    # путь от входа до каждой станции: список (развилка, индекс ребёнка)
    route = {}
    for st in g["st"]:
        path = []; y = st
        while g["parent"][y] is not None:
            p = g["parent"][y]
            if len(g["children"][p]) == 2:
                path.append((p, g["children"][p].index(y)))
            y = p
        route[st] = path[::-1]
    events = []
    for t0, col in sched:
        for sw, idx in route[target[col]]:
            events.append((t0 + (2 * dist[sw] - 1) * MS_PER_CELL // 2, sw, idx))
    events.sort()
    state = dict(init_state); tog = []
    last = {}
    for t_enter, sw, idx in events:
        if state[sw] != idx:
            t = max(t_enter - 300, last.get(sw, -1) + 1)
            assert t <= t_enter
            tog.append((t, sw)); state[sw] = idx
        last[sw] = t_enter
    return tog

if __name__ == "__main__":
    mism = 0; total = 0; perfect_ok = 0; runs = 0
    arrivals = {}
    for L in (1, 6, 12, 15):
        for seed in range(4):
            g = gen2.generate(L, seed)
            rng = random.Random(f"s{seed}")
            sched = schedule(g, L, rng)
            stations = sorted(g["st"])
            cols = list(range(g["n"])); rng.shuffle(cols)
            cos = dict(zip(stations, cols))
            sws = [x for x in g["parent"] if len(g["children"][x]) == 2]
            init = {x: rng.randint(0, 1) for x in sws}
            rnd_tog = sorted((rng.randrange(GAME_MS), rng.choice(sws)) for _ in range(80))
            for tog in (rnd_tog, perfect_toggles(g, sched, cos, init)):
                a = judge(g, sched, cos, init, tog); b = tick_sim(g, sched, cos, init, tog)
                total += 1; mism += (a != b)
            p = judge(g, sched, cos, init, perfect_toggles(g, sched, cos, init))
            runs += 1; perfect_ok += all(x[3] for x in p)
            arrivals.setdefault(L, []).append(len(p))
    print("судья vs покадровая:", total - mism, "из", total, "совпали")
    print("идеальный игрок 100%:", perfect_ok, "из", runs)
    for L, v in arrivals.items():
        print(f"L{L}: прибытий за партию avg={sum(v)/len(v):.1f} min={min(v)} max={max(v)}")

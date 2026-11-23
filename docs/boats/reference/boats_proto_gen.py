"""Образец генератора поля «Корабликов» (прототип, НЕ для продакшена): покрывающее дерево с ≤2 потомками + срезка листьев.

Запуск: python3 boats_proto_gen.py [число_зёрен] — сводка по уровням 1–15 (см. docs/boats/analysis.md §7).
В продакшене (games_core/boats.py) переписать чисто по docs/boats/tz.md §5, сохранив алгоритм и константы.
"""
import math, random, time
from collections import Counter

DIRS = {"N": (-1, 0), "E": (0, 1), "S": (1, 0), "W": (0, -1)}

def level_cfg(L):
    n = min(L + 2, 14)
    if n <= 4:   dims = (5, 4)
    elif n <= 6: dims = (6, 4)
    elif n <= 9: dims = (6, 5)
    else:        dims = (7, 5)
    return n, dims

def max_depth_allowed(n):
    return math.ceil(math.log2(n)) + 3

BIAS = 0.6

class Fail(Exception):
    pass

def try_generate(n, rows, cols, rng, fill_target=0.85, branch_bias=0.0):
    inb = lambda r, c: 0 <= r < rows and 0 <= c < cols
    edges = []
    for c in range(cols):
        edges += [(0, c), (rows - 1, c)]
    for r in range(1, rows - 1):
        edges += [(r, 0), (r, cols - 1)]
    src = rng.choice(edges)
    parent = {src: None}
    children = {src: []}
    cap = {src: 1}
    # 1) рост «по Приму»: случайное ребро из фронта
    frontier = []
    def push(p):
        for dr, dc in DIRS.values():
            q = (p[0] + dr, p[1] + dc)
            if inb(*q) and q not in parent:
                frontier.append((p, q))
    push(src)
    while frontier:
        i = rng.randrange(len(frontier))
        if branch_bias and rng.random() < branch_bias:
            # охотнее даём второго потомка тому, у кого уже есть один
            idx = [j for j, (pp, qq) in enumerate(frontier)
                   if qq not in parent and len(children[pp]) == 1 and cap[pp] == 2]
            if idx:
                i = rng.choice(idx)
        p, q = frontier[i]
        frontier[i] = frontier[-1]; frontier.pop()
        if q in parent or len(children[p]) >= cap[p]:
            continue
        # не пускаем вход по краю поля вдоль стены (вход смотрит внутрь)
        if p == src:
            pr, pc = src
            inward = (pr == 0 and q[0] == 1) or (pr == rows - 1 and q[0] == rows - 2) or \
                     (pc == 0 and q[1] == 1) or (pc == cols - 1 and q[1] == cols - 2)
            if not inward:
                continue
        parent[q] = p; children[q] = []; children[p].append(q)
        cap[q] = 1 if p == src else 2      # первая клетка после входа — канал
        push(q)
    leaves = lambda: [x for x in parent if not children[x] and x != src]
    def nsw(x):  # число развилок на пути от входа до x
        k = 0
        while x is not None:
            if len(children[x]) == 2: k += 1
            x = parent[x]
        return k
    def remove(x):
        p = parent.pop(x); children.pop(x); children[p].remove(x)
    # 2) срезаем листья у развилок, пока листьев больше n (глубокие — охотнее)
    while True:
        lv = leaves()
        if len(lv) <= n:
            break
        cand = [x for x in lv if len(children[parent[x]]) == 2]
        if not cand:
            # остались только «хвосты» — укорачиваем случайный
            remove(rng.choice(lv)); continue
        w = [1 + nsw(x) ** 2 for x in cand]
        remove(rng.choices(cand, w)[0])
    if len(leaves()) != n:
        raise Fail
    # 3) укорачиваем хвосты каналов до целевой заполненности
    while len(parent) > fill_target * rows * cols:
        tails = [x for x in leaves() if len(children[parent[x]]) == 1 and parent[x] != src
                 and parent[parent[x]] is not None]
        if not tails:
            break
        remove(rng.choice(tails))
    # проверки
    lv = leaves()
    sw = [x for x in parent if len(children[x]) == 2]
    assert len(sw) == n - 1 and len(lv) == n
    first = children[src][0]
    if len(children[first]) != 1:
        raise Fail
    depths = [nsw(x) for x in lv]
    if max(depths) > max_depth_allowed(n):
        raise Fail
    return dict(n=n, rows=rows, cols=cols, src=src, parent=parent, children=children,
                st=lv, sw=sw, depths=depths)

def generate(L, seed, max_tries=500, fill_target=0.85, branch_bias=None):
    if branch_bias is None:
        branch_bias = BIAS
    n, (rows, cols) = level_cfg(L)
    for t in range(max_tries):
        rng = random.Random(f"{seed}:{t}")
        try:
            g = try_generate(n, rows, cols, rng, fill_target, branch_bias)
            g["tries"] = t + 1
            return g
        except Fail:
            continue
    return None

def side(a, b):
    dr, dc = b[0] - a[0], b[1] - a[1]
    return {(-1, 0): "N", (1, 0): "S", (0, 1): "E", (0, -1): "W"}[(dr, dc)]

def ascii(g):
    rows, cols = g["rows"], g["cols"]
    names = "ABCDEFGHIJKLMNOP"
    stn = {x: names[i] for i, x in enumerate(sorted(g["st"]))}
    out = []
    for r in range(rows):
        line = ""
        for c in range(cols):
            x = (r, c)
            if x not in g["parent"]: ch = "  ·  "
            elif x == g["src"]: ch = " >>> "
            elif x in stn: ch = f" [{stn[x]}] "
            else:
                sides = {side(x, g["parent"][x])} | {side(x, y) for y in g["children"][x]}
                if len(sides) == 3: ch = " (Y) "
                elif sides == {"N", "S"}: ch = "  │  "
                elif sides == {"E", "W"}: ch = "─────"
                else:
                    ch = {frozenset("NE"): "  └──", frozenset("NW"): "──┘  ",
                          frozenset("SE"): "  ┌──", frozenset("SW"): "──┐  "}[frozenset(sides)]
            line += ch
        out.append(line)
    return "\n".join(out)

if __name__ == "__main__":
    import sys
    seeds = int(sys.argv[1]) if len(sys.argv) > 1 else 1000
    for L in range(1, 16):
        n, dims = level_cfg(L)
        ok = 0; tries = []; times = []; dep = Counter(); fill = []; first = []
        for s in range(seeds):
            t0 = time.perf_counter()
            g = generate(L, s)
            times.append(time.perf_counter() - t0)
            if g:
                ok += 1; tries.append(g["tries"]); dep[max(g["depths"])] += 1
                fill.append(len(g["parent"]) / (g["rows"] * g["cols"]))
                first.append(min(g["depths"]))
        times.sort()
        print(f"L{L:2} n={n:2} {dims[0]}x{dims[1]} ok={100*ok/seeds:5.1f}% "
              f"tries avg={sum(tries)/max(1,len(tries)):5.1f} max={max(tries or [0]):3} "
              f"t50={times[len(times)//2]*1000:5.1f}ms t99={times[int(len(times)*.99)]*1000:6.1f}ms "
              f"fill={sum(fill)/max(1,len(fill)):.2f} maxdepth={dict(sorted(dep.items()))}", flush=True)

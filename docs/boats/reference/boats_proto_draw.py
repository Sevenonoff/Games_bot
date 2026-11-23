"""Рисует сгенерированные поля в ASCII. Запуск: python3 boats_proto_draw.py 1:1 12:5 (уровень:зерно)."""
import sys, random
sys.path.insert(0, ".")
import boats_proto_gen as gen2
from boats_proto_gen import side

def draw(g):
    rows, cols = g["rows"], g["cols"]
    names = "ABCDEFGHIJKLMNOP"
    stn = {x: names[i] for i, x in enumerate(sorted(g["st"]))}
    def links(x):
        s = set()
        if x in g["parent"]:
            if g["parent"][x] is not None: s.add(side(x, g["parent"][x]))
            s |= {side(x, y) for y in g["children"][x]}
        return s
    out = []
    for r in range(rows):
        line = ""; below = ""
        for c in range(cols):
            x = (r, c); L = links(x)
            if x not in g["parent"]: sym = " · "
            elif x == g["src"]: sym = " ▶ "
            elif x in stn: sym = f"[{stn[x]}]"
            elif len(g["children"][x]) == 2: sym = "(Y)"
            else: sym = " ┼ " if False else {frozenset("NS"): " │ ", frozenset("EW"): "───",
                    frozenset("NE"): " └─", frozenset("NW"): "─┘ ", frozenset("SE"): " ┌─",
                    frozenset("SW"): "─┐ "}[frozenset(L)]
            line += sym
            if c < cols - 1:
                line += "──" if "E" in L else "  "
            below += (" │ " if "S" in L else "   ") + ("  " if c < cols - 1 else "")
        out.append(line)
        if r < rows - 1:
            out.append(below)
    return "\n".join(out)

if __name__ == "__main__":
    for L, s in [(int(a.split(":")[0]), int(a.split(":")[1])) for a in sys.argv[1:]]:
        g = gen2.generate(L, s)
        print(f"Уровень {L}, зерно {s}: причалов {g['n']}, развилок {len(g['sw'])}, поле {g['cols']}×{g['rows']}, "
              f"развилок до причалов: {min(g['depths'])}–{max(g['depths'])}")
        print(draw(g)); print()

"""Стиль C «Сказочная карта»: бумага, тушь с дрожанием линии, акварельные пятна, пунктир пути."""
import math
import random

from common import DENSE, TRAIL_END, W, H, f, path_points, render, svg_doc, _near_path
from heroes import hero

INK = "#4a3424"


def defs():
    return (
        '<filter id="paper" x="0" y="0" width="100%" height="100%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves="3" seed="4" result="n"/>'
        '<feColorMatrix in="n" type="matrix" values="0 0 0 0 0.45  0 0 0 0 0.33  0 0 0 0 0.2  0 0 0 0.18 0"/>'
        '<feComposite in2="SourceGraphic" operator="in"/></filter>'
        '<filter id="blotch" x="0" y="0" width="100%" height="100%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.012" numOctaves="2" seed="9" result="n"/>'
        '<feColorMatrix in="n" type="matrix" values="0 0 0 0 0.55  0 0 0 0 0.4  0 0 0 0 0.2  0 0 0 0.5 -0.12"/>'
        '<feComposite in2="SourceGraphic" operator="in"/></filter>'
        '<filter id="wc" x="-20%" y="-20%" width="140%" height="140%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.05" numOctaves="2" seed="2" result="t"/>'
        '<feDisplacementMap in="SourceGraphic" in2="t" scale="6" result="d"/>'
        '<feGaussianBlur in="d" stdDeviation="1.2"/></filter>'
        '<filter id="wobble" x="-10%" y="-10%" width="120%" height="120%">'
        '<feTurbulence type="fractalNoise" baseFrequency="0.04" numOctaves="1" seed="5" result="t"/>'
        '<feDisplacementMap in="SourceGraphic" in2="t" scale="3"/></filter>'
        '<radialGradient id="burn" cx="0.5" cy="0.5" r="0.72">'
        '<stop offset="0.62" stop-color="#7a4a1c" stop-opacity="0"/>'
        '<stop offset="0.92" stop-color="#7a4a1c" stop-opacity="0.35"/>'
        '<stop offset="1" stop-color="#5a3010" stop-opacity="0.7"/></radialGradient>'
        '<radialGradient id="glowm"><stop offset="0" stop-color="#fff3b0" stop-opacity="0.9"/>'
        '<stop offset="1" stop-color="#fff3b0" stop-opacity="0"/></radialGradient>'
    )


def wc(svg, op=0.55):
    """Акварельная заливка: рваные края + лёгкое размытие."""
    return f'<g filter="url(#wc)" opacity="{op}">{svg}</g>'


def ink(svg):
    return f'<g filter="url(#wobble)" stroke="{INK}" fill="none" stroke-linecap="round" stroke-linejoin="round">{svg}</g>'


def tree_ink(x, y, s, rng):
    """Дерево-«облачко» тушью: обвод кроны дугами."""
    r = 11 * s
    d = f"M{f(x - r)} {f(y - 10 * s)} "
    n = 6
    for i in range(n):
        a0 = math.pi + i * math.pi / (n - 1) * 1.0
        ax, ay = x + math.cos(a0 + math.pi / (n - 1)) * r, y - 14 * s + math.sin(a0 + math.pi / (n - 1)) * r * 0.9
        d += f"Q{f(x + math.cos(a0 + math.pi / (2 * (n - 1))) * r * 1.35)} {f(y - 14 * s + math.sin(a0 + math.pi / (2 * (n - 1))) * r * 1.25)} {f(ax)} {f(ay)} "
    d += f"Q{f(x)} {f(y - 2 * s)} {f(x - r)} {f(y - 10 * s)}"
    fill = wc(f'<circle cx="{f(x)}" cy="{f(y - 14 * s)}" r="{f(r * 1.05)}" fill="{rng.choice(["#6f9e4a", "#7fae52", "#5d8f45"])}"/>', 0.6)
    trunk = f'<path d="M{f(x)} {f(y - 4 * s)} L{f(x)} {f(y + 3 * s)}" stroke-width="1.6"/>'
    hatch = "".join(f'<path d="M{f(x + 3 * s + k * 2.5 * s)} {f(y - 8 * s - k * 1.5 * s)} l{f(3 * s)} {f(-3 * s)}" stroke-width="0.8"/>' for k in range(3))
    return fill + ink(f'<path d="{d}" stroke-width="1.4"/>' + trunk + hatch)


def pine_ink(x, y, s, rng):
    pts = f"{f(x)},{f(y - 26 * s)} {f(x - 9 * s)},{f(y - 2 * s)} {f(x + 9 * s)},{f(y - 2 * s)}"
    fill = wc(f'<polygon points="{pts}" fill="#4f7f45"/>', 0.6)
    lines = (f'<path d="M{f(x)} {f(y - 26 * s)} L{f(x - 9 * s)} {f(y - 2 * s)} L{f(x + 9 * s)} {f(y - 2 * s)} Z" stroke-width="1.4"/>'
             f'<path d="M{f(x)} {f(y - 2 * s)} L{f(x)} {f(y + 3 * s)}" stroke-width="1.5"/>')
    lines += "".join(f'<path d="M{f(x + 1 * s)} {f(y - (6 + 5 * k) * s)} l{f((5 - k) * s)} {f(2 * s)}" stroke-width="0.8"/>' for k in range(3))
    return fill + ink(lines)


def hill_ink(x, y, s):
    fill = wc(f'<path d="M{f(x - 26 * s)} {f(y)} Q{f(x)} {f(y - 28 * s)} {f(x + 26 * s)} {f(y)} Z" fill="#a9b86a"/>', 0.5)
    lines = f'<path d="M{f(x - 26 * s)} {f(y)} Q{f(x)} {f(y - 28 * s)} {f(x + 26 * s)} {f(y)}" stroke-width="1.5"/>'
    lines += "".join(f'<path d="M{f(x + (4 + k * 5) * s)} {f(y - (10 - k * 2.5) * s)} l{f(2 * s)} {f(5 * s)}" stroke-width="0.8"/>' for k in range(4))
    return fill + ink(lines)


def house_ink(x, y, s):
    fill = wc(f'<rect x="{f(x - 14 * s)}" y="{f(y - 16 * s)}" width="{f(28 * s)}" height="{f(16 * s)}" fill="#e8c9a0"/>'
              f'<polygon points="{f(x - 18 * s)},{f(y - 15 * s)} {f(x)},{f(y - 32 * s)} {f(x + 18 * s)},{f(y - 15 * s)}" fill="#c9553f"/>', 0.7)
    lines = (f'<path d="M{f(x - 14 * s)} {f(y)} L{f(x - 14 * s)} {f(y - 16 * s)} M{f(x + 14 * s)} {f(y)} L{f(x + 14 * s)} {f(y - 16 * s)} '
             f'M{f(x - 15 * s)} {f(y)} L{f(x + 15 * s)} {f(y)}" stroke-width="1.5"/>'
             f'<path d="M{f(x - 18 * s)} {f(y - 15 * s)} L{f(x)} {f(y - 32 * s)} L{f(x + 18 * s)} {f(y - 15 * s)} Z" stroke-width="1.5"/>'
             f'<rect x="{f(x - 3 * s)}" y="{f(y - 9 * s)}" width="{f(6 * s)}" height="{f(9 * s)}" stroke-width="1.2"/>'
             f'<rect x="{f(x + 6 * s)}" y="{f(y - 12 * s)}" width="{f(5 * s)}" height="{f(5 * s)}" stroke-width="1"/>')
    lines += "".join(f'<path d="M{f(x - 12 * s + k * 4 * s)} {f(y - 18 * s - k * 2 * s)} l{f(3 * s)} {f(-2 * s)}" stroke-width="0.8"/>' for k in range(4))
    return fill + ink(lines)


def mill_ink(x, y, s):
    fill = wc(f'<polygon points="{f(x - 10 * s)},{f(y)} {f(x - 6 * s)},{f(y - 30 * s)} {f(x + 6 * s)},{f(y - 30 * s)} {f(x + 10 * s)},{f(y)}" fill="#e8d2ad"/>', 0.7)
    lines = f'<path d="M{f(x - 10 * s)} {f(y)} L{f(x - 6 * s)} {f(y - 30 * s)} L{f(x + 6 * s)} {f(y - 30 * s)} L{f(x + 10 * s)} {f(y)} Z" stroke-width="1.5"/>'
    cx, cy = x, y - 30 * s
    for a in (20, 110, 200, 290):
        r = math.radians(a)
        ex, ey = cx + math.cos(r) * 24 * s, cy + math.sin(r) * 24 * s
        px, py = -math.sin(r) * 5 * s, math.cos(r) * 5 * s
        lines += (f'<path d="M{f(cx)} {f(cy)} L{f(ex)} {f(ey)}" stroke-width="1.4"/>'
                  f'<path d="M{f(cx + (ex - cx) * 0.3)} {f(cy + (ey - cy) * 0.3)} L{f(cx + (ex - cx) * 0.3 + px)} {f(cy + (ey - cy) * 0.3 + py)} '
                  f'L{f(ex + px)} {f(ey + py)} L{f(ex)} {f(ey)}" stroke-width="1"/>')
    return fill + ink(lines)


def lake(cx, cy, rx, ry):
    fill = wc(f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" fill="#6fa8c9"/>', 0.7)
    lines = f'<ellipse cx="{cx}" cy="{cy}" rx="{rx}" ry="{ry}" stroke-width="1.6"/>'
    for k in range(1, 4):
        lines += f'<ellipse cx="{cx}" cy="{cy}" rx="{rx + 6 * k}" ry="{ry + 4 * k}" stroke-width="0.7" stroke-dasharray="{3 + k} {4 + k * 2}" opacity="{0.7 - k * 0.15}"/>'
    for dx, dy in ((-30, -6), (10, 4), (35, -4)):
        lines += f'<path d="M{cx + dx - 6} {cy + dy} q3 -3 6 0 q3 3 6 0" stroke-width="0.9"/>'
    return fill + ink(lines)


def compass(x, y, r):
    o = wc(f'<circle cx="{x}" cy="{y}" r="{r}" fill="#e9d3a5"/>', 0.6)
    lines = f'<circle cx="{x}" cy="{y}" r="{r}" stroke-width="1.2"/><circle cx="{x}" cy="{y}" r="{r - 4}" stroke-width="0.7"/>'
    o += ink(lines)
    for a, ln, col in ((-90, 1.0, "#b8432f"), (90, 0.75, INK), (0, 0.75, INK), (180, 0.75, INK)):
        rad = math.radians(a)
        tip = (x + math.cos(rad) * r * ln, y + math.sin(rad) * r * ln)
        side = (math.cos(rad + math.pi / 2) * 4, math.sin(rad + math.pi / 2) * 4)
        o += f'<polygon points="{f(tip[0])},{f(tip[1])} {f(x + side[0])},{f(y + side[1])} {f(x - side[0])},{f(y - side[1])}" fill="{col}" stroke="{INK}" stroke-width="0.8"/>'
    o += f'<text x="{x}" y="{y - r - 4}" font-family="DejaVu Sans" font-size="11" fill="{INK}" text-anchor="middle">С</text>'
    return o


def scene(step=9, n=25, hero_kind="bear"):
    rng = random.Random(11)
    o = f'<rect width="{W}" height="{H}" fill="#f1e2bf"/>'
    o += f'<rect width="{W}" height="{H}" fill="#fff" filter="url(#blotch)"/>'
    o += f'<rect width="{W}" height="{H}" fill="#fff" filter="url(#paper)"/>'
    # луга акварелью
    for _ in range(22):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        o += wc(f'<ellipse cx="{f(x)}" cy="{f(y)}" rx="{f(rng.uniform(60, 120))}" ry="{f(rng.uniform(30, 55))}" fill="{rng.choice(["#a9c47a", "#c2d08a", "#9dbb6e"])}"/>', 0.5)
    o += lake(400, 198, 70, 22)
    # путь: двойная пунктирная линия тушью
    d = "M" + " L".join(f"{f(x)} {f(y)}" for x, y in DENSE[::4] + [TRAIL_END])
    o += wc(f'<path d="{d}" stroke="#d9b98a" stroke-width="26" fill="none" stroke-linecap="round" stroke-linejoin="round"/>', 0.55)
    o += ink(f'<path d="{d}" stroke-width="1.2" stroke-dasharray="7 6" transform="translate(0 -13)" opacity="0.6"/>'
             f'<path d="{d}" stroke-width="1.2" stroke-dasharray="7 6" transform="translate(0 13)" opacity="0.6"/>')
    objs = []
    objs.append((100, house_ink(205, 100, 1.4)))
    objs.append((370, mill_ink(615, 370, 1.4)))
    for x, y in ((50, 92), (95, 72), (150, 96), (350, 80), (440, 96), (555, 78), (160, 236), (240, 232), (640, 236),
                 (90, 368), (200, 372), (500, 372), (300, 368), (560, 236)):
        objs.append((y, tree_ink(x, y, rng.uniform(1.0, 1.25), rng) if rng.random() < 0.6 else pine_ink(x, y, 1.2, rng)))
    for x, y in ((420, 372), (700, 372), (300, 236)):
        objs.append((y, hill_ink(x, y, 1.0)))
    for y, s in sorted(objs):
        o += s
    # стоянки пути: кружки тушью, пройденные — с крестиком/закрашены
    pts = path_points(n)
    for i, (x, y) in enumerate(pts):
        if i < step:
            o += wc(f'<circle cx="{f(x)}" cy="{f(y)}" r="9" fill="#c9553f"/>', 0.8)
            o += ink(f'<circle cx="{f(x)}" cy="{f(y)}" r="9" stroke-width="1.4"/>'
                     f'<path d="M{f(x - 4)} {f(y)} l3 3.5 l6 -7" stroke="#fff6e0" stroke-width="2"/>')
        else:
            o += f'<circle cx="{f(x)}" cy="{f(y)}" r="9" fill="#f6ead0"/>'
            o += ink(f'<circle cx="{f(x)}" cy="{f(y)}" r="9" stroke-width="1.4"/>')
    o += compass(735, 395, 30)
    # «туман» — неизведанные земли: штриховка + облака тушью
    fog = ""
    for cx, cy, r in ((790, 30, 75), (705, 50, 50), (775, 140, 62), (715, 160, 40), (650, 18, 34), (760, 95, 60)):
        fog += f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#f8f1e0"/>'
    o += f'<g filter="url(#wc)">{fog}</g>'
    lines = ""
    for cx, cy, r in ((705, 50, 45), (715, 160, 35), (650, 18, 30), (775, 140, 58)):
        lines += f'<path d="M{cx - r} {cy + r * 0.3} A{r} {r * 0.8} 0 0 1 {cx + r * 0.9} {cy - r * 0.1}" stroke-width="1.3"/>'
    o += ink(lines)
    o += (f'<text x="745" y="112" font-family="DejaVu Sans" font-size="13" fill="{INK}" text-anchor="middle" '
          f'font-style="italic" opacity="0.85">Земли</text><text x="745" y="128" font-family="DejaVu Sans" '
          f'font-size="13" fill="{INK}" text-anchor="middle" opacity="0.85">неведомые</text>')
    o += f'<rect width="{W}" height="{H}" fill="url(#burn)"/>'
    o += f'<rect x="6" y="6" width="{W - 12}" height="{H - 12}" fill="none" stroke="{INK}" stroke-width="1.5" opacity="0.6"/>'
    o += f'<rect x="11" y="11" width="{W - 22}" height="{H - 22}" fill="none" stroke="{INK}" stroke-width="0.7" opacity="0.5"/>'
    hx, hy = pts[step]
    o += f'<ellipse cx="{f(hx)}" cy="{f(hy)}" rx="26" ry="18" fill="url(#glowm)"/>'
    dd, g = hero(hero_kind, hx, hy + 3, 1.0)
    o += g
    return svg_doc(o, defs() + dd)


if __name__ == "__main__":
    render(scene(), "C_map.png")

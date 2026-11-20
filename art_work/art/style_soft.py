"""Стиль A «Мягкий объём»: карта как в мобильных играх-«сагах» — градиенты, мягкие тени, контур."""
import math
import random

from common import DENSE, TRAIL_END, W, H, f, path_points, pts_path, render, shade, svg_doc, _near_path
from heroes import hero

SUN = (-0.6, -0.8)   # свет сверху слева, тени падают вправо-вниз


def defs_common():
    return (
        '<radialGradient id="grass" cx="0.45" cy="0.45" r="0.75">'
        '<stop offset="0" stop-color="#b6e27a"/><stop offset="0.7" stop-color="#93cf5c"/>'
        '<stop offset="1" stop-color="#77b648"/></radialGradient>'
        '<radialGradient id="vign" cx="0.5" cy="0.5" r="0.75">'
        '<stop offset="0.6" stop-color="#0b3d10" stop-opacity="0"/>'
        '<stop offset="1" stop-color="#0b3d10" stop-opacity="0.28"/></radialGradient>'
        '<radialGradient id="crown" cx="0.35" cy="0.3" r="0.75">'
        '<stop offset="0" stop-color="#9ee06a"/><stop offset="0.6" stop-color="#5fae43"/>'
        '<stop offset="1" stop-color="#3f8a34"/></radialGradient>'
        '<radialGradient id="crown2" cx="0.35" cy="0.3" r="0.75">'
        '<stop offset="0" stop-color="#c3e66a"/><stop offset="0.6" stop-color="#86bf3e"/>'
        '<stop offset="1" stop-color="#5f9a2c"/></radialGradient>'
        '<linearGradient id="trunk" x1="0" x2="1"><stop offset="0" stop-color="#a5703d"/>'
        '<stop offset="1" stop-color="#7a4c24"/></linearGradient>'
        '<radialGradient id="pond" cx="0.4" cy="0.35" r="0.7">'
        '<stop offset="0" stop-color="#8fdcff"/><stop offset="0.7" stop-color="#4fb3e8"/>'
        '<stop offset="1" stop-color="#3a95cf"/></radialGradient>'
        '<linearGradient id="stone" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fbf8f1"/>'
        '<stop offset="1" stop-color="#dcd3c3"/></linearGradient>'
        '<linearGradient id="gold" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffe680"/>'
        '<stop offset="1" stop-color="#f5b324"/></linearGradient>'
        '<radialGradient id="glow"><stop offset="0" stop-color="#fff6b0" stop-opacity="0.95"/>'
        '<stop offset="0.55" stop-color="#ffe45c" stop-opacity="0.55"/>'
        '<stop offset="1" stop-color="#ffe45c" stop-opacity="0"/></radialGradient>'
        '<linearGradient id="cloud" x1="0" y1="0" x2="0" y2="1"><stop offset="0.45" stop-color="#ffffff"/>'
        '<stop offset="1" stop-color="#d5dfee"/></linearGradient>'
        '<linearGradient id="roof" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#f26b5b"/>'
        '<stop offset="1" stop-color="#c8433a"/></linearGradient>'
        '<filter id="blur4" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="4"/></filter>'
        '<filter id="blur2" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="2"/></filter>'
        '<filter id="blur8" x="-50%" y="-50%" width="200%" height="200%"><feGaussianBlur stdDeviation="8"/></filter>'
    )


def shadow(x, y, rx, ry, op=0.22):
    return f'<ellipse cx="{f(x)}" cy="{f(y)}" rx="{f(rx)}" ry="{f(ry)}" fill="#1d4a12" opacity="{op}" filter="url(#blur2)"/>'


def tree(x, y, s=1.0, crown="crown"):
    """Основание ствола в (x, y)."""
    o = shadow(x + 10 * s, y + 1, 22 * s, 7 * s)
    o += (f'<path d="M{f(x - 4 * s)} {f(y)} L{f(x - 3 * s)} {f(y - 22 * s)} L{f(x + 3 * s)} {f(y - 22 * s)} '
          f'L{f(x + 4 * s)} {f(y)} Z" fill="url(#trunk)" stroke="#5a3a1c" stroke-width="1.5"/>')
    o += f'<g stroke="#2f6b28" stroke-width="1.8">'
    for dx, dy, r in ((-11, -26, 14), (11, -27, 14), (0, -38, 17)):
        o += f'<circle cx="{f(x + dx * s)}" cy="{f(y + dy * s)}" r="{f(r * s)}" fill="url(#{crown})"/>'
    o += '</g>'
    # без внутренних контуров: заливка поверх
    for dx, dy, r in ((-11, -26, 13.1), (11, -27, 13.1), (0, -38, 16.1)):
        o += f'<circle cx="{f(x + dx * s)}" cy="{f(y + dy * s)}" r="{f(r * s)}" fill="url(#{crown})"/>'
    o += f'<ellipse cx="{f(x - 6 * s)}" cy="{f(y - 45 * s)}" rx="{f(6 * s)}" ry="{f(3.2 * s)}" fill="#fff" opacity="0.35" transform="rotate(-25 {f(x - 6 * s)} {f(y - 45 * s)})"/>'
    return o


def apple_tree(x, y, s=1.0, rng=None):
    o = tree(x, y, s, "crown")
    rng = rng or random.Random(int(x * 7 + y))
    for _ in range(6):
        ax, ay = x + rng.uniform(-18, 18) * s, y + rng.uniform(-44, -20) * s
        o += f'<circle cx="{f(ax)}" cy="{f(ay)}" r="{f(2.6 * s)}" fill="#ef4b3f" stroke="#a52a22" stroke-width="0.8"/>'
    return o


def bush(x, y, s=1.0, berries=False, rng=None):
    o = shadow(x + 6 * s, y + 1, 18 * s, 5 * s)
    parts = ((-9, -7, 9), (9, -7, 9), (0, -12, 11))
    o += '<g stroke="#2f6b28" stroke-width="1.6">'
    for dx, dy, r in parts:
        o += f'<circle cx="{f(x + dx * s)}" cy="{f(y + dy * s)}" r="{f(r * s)}" fill="url(#crown)"/>'
    o += '</g>'
    for dx, dy, r in parts:
        o += f'<circle cx="{f(x + dx * s)}" cy="{f(y + dy * s)}" r="{f((r - 0.8) * s)}" fill="url(#crown)"/>'
    if berries:
        rng = rng or random.Random(int(x + y * 3))
        for _ in range(5):
            o += (f'<circle cx="{f(x + rng.uniform(-14, 14) * s)}" cy="{f(y + rng.uniform(-17, -4) * s)}" '
                  f'r="{f(1.9 * s)}" fill="#e2366b"/>')
    return o


def flower(x, y, col, s=1.0):
    o = f'<path d="M{f(x)} {f(y)} l0 {f(7 * s)}" stroke="#3f8a34" stroke-width="{f(1.4 * s)}"/>'
    for k in range(5):
        a = k * 2 * math.pi / 5 - math.pi / 2
        o += (f'<circle cx="{f(x + math.cos(a) * 3.1 * s)}" cy="{f(y + math.sin(a) * 3.1 * s)}" '
              f'r="{f(2.5 * s)}" fill="{col}" stroke="{shade(col, 0.75)}" stroke-width="0.6"/>')
    o += f'<circle cx="{f(x)}" cy="{f(y)}" r="{f(1.8 * s)}" fill="#ffb627"/>'
    return o


def tuft(x, y, s=1.0, col="#5f9e3c"):
    return (f'<path d="M{f(x - 3 * s)} {f(y)} q-1 {f(-4 * s)} {f(-3 * s)} {f(-6 * s)} M{f(x)} {f(y)} '
            f'q0 {f(-5 * s)} {f(1 * s)} {f(-8 * s)} M{f(x + 3 * s)} {f(y)} q1 {f(-4 * s)} {f(3 * s)} {f(-6 * s)}" '
            f'fill="none" stroke="{col}" stroke-width="{f(1.3 * s)}" stroke-linecap="round" opacity="0.8"/>')


def house(x, y, s=1.0):
    """Домик, низ стены в (x, y)."""
    o = shadow(x + 14 * s, y + 2, 38 * s, 8 * s, 0.25)
    w, h = 26 * s, 26 * s
    o += (f'<rect x="{f(x - w)}" y="{f(y - h)}" width="{f(2 * w)}" height="{f(h)}" fill="#fff1d6" '
          f'stroke="#7a5236" stroke-width="1.8"/>')
    o += f'<rect x="{f(x + w * 0.35)}" y="{f(y - h)}" width="{f(w * 0.65)}" height="{f(h)}" fill="#eedbb6"/>'
    o += (f'<path d="M{f(x - w - 6 * s)} {f(y - h + 2 * s)} L{f(x)} {f(y - h - 26 * s)} '
          f'L{f(x + w + 6 * s)} {f(y - h + 2 * s)} Z" fill="url(#roof)" stroke="#8a2e26" stroke-width="1.8" '
          f'stroke-linejoin="round"/>')
    o += (f'<rect x="{f(x + 10 * s)}" y="{f(y - h - 26 * s)}" width="{f(7 * s)}" height="{f(14 * s)}" '
          f'fill="#b5654c" stroke="#7a3a2a" stroke-width="1.4"/>')
    o += (f'<rect x="{f(x - 6 * s)}" y="{f(y - 15 * s)}" width="{f(12 * s)}" height="{f(15 * s)}" rx="{f(5 * s)}" '
          f'fill="#9a5d34" stroke="#5e3a1e" stroke-width="1.4"/>')
    for dx in (-18, 12):
        o += (f'<rect x="{f(x + dx * s)}" y="{f(y - 19 * s)}" width="{f(8 * s)}" height="{f(8 * s)}" rx="1.5" '
              f'fill="#8fd3ff" stroke="#5e3a1e" stroke-width="1.4"/>')
    # дымок
    for i, (dx, dy, r) in enumerate(((14, -58, 4), (18, -66, 5), (24, -75, 6))):
        o += f'<circle cx="{f(x + dx * s)}" cy="{f(y + dy * s)}" r="{f(r * s)}" fill="#fff" opacity="{0.7 - i * 0.15}"/>'
    return o


def windmill(x, y, s=1.0, ang=18):
    o = shadow(x + 16 * s, y + 2, 30 * s, 7 * s, 0.25)
    o += (f'<path d="M{f(x - 15 * s)} {f(y)} L{f(x - 9 * s)} {f(y - 46 * s)} L{f(x + 9 * s)} {f(y - 46 * s)} '
          f'L{f(x + 15 * s)} {f(y)} Z" fill="#fff4e0" stroke="#7a5236" stroke-width="1.8" stroke-linejoin="round"/>')
    o += (f'<path d="M{f(x + 3 * s)} {f(y)} L{f(x + 4 * s)} {f(y - 46 * s)} L{f(x + 9 * s)} {f(y - 46 * s)} '
          f'L{f(x + 15 * s)} {f(y)} Z" fill="#ead6b4"/>')
    o += (f'<path d="M{f(x - 13 * s)} {f(y - 45 * s)} Q{f(x)} {f(y - 66 * s)} {f(x + 13 * s)} {f(y - 45 * s)} Z" '
          f'fill="url(#roof)" stroke="#8a2e26" stroke-width="1.8"/>')
    o += (f'<rect x="{f(x - 5 * s)}" y="{f(y - 14 * s)}" width="{f(10 * s)}" height="{f(14 * s)}" rx="{f(5 * s)}" '
          f'fill="#9a5d34" stroke="#5e3a1e" stroke-width="1.3"/>')
    cx, cy = x, y - 46 * s
    for k in range(4):
        a = ang + k * 90
        o += (f'<g transform="rotate({a} {f(cx)} {f(cy)})"><rect x="{f(cx - 1.5 * s)}" y="{f(cy - 40 * s)}" '
              f'width="{f(3 * s)}" height="{f(40 * s)}" fill="#8a5a30"/>'
              f'<rect x="{f(cx + 1.5 * s)}" y="{f(cy - 38 * s)}" width="{f(10 * s)}" height="{f(28 * s)}" '
              f'fill="#fffaf0" stroke="#8a5a30" stroke-width="1.3"/></g>')
    o += f'<circle cx="{f(cx)}" cy="{f(cy)}" r="{f(3.5 * s)}" fill="#5e3a1e"/>'
    return o


def fence(x0, x1, y):
    o = f'<g stroke="#7a5236" stroke-width="1.4">'
    o += f'<rect x="{f(x0)}" y="{f(y - 12)}" width="{f(x1 - x0)}" height="3" fill="#e9c58f"/>'
    o += f'<rect x="{f(x0)}" y="{f(y - 6)}" width="{f(x1 - x0)}" height="3" fill="#e9c58f"/>'
    x = x0
    while x <= x1:
        o += f'<path d="M{f(x - 2.5)} {f(y)} L{f(x - 2.5)} {f(y - 15)} L{f(x)} {f(y - 18)} L{f(x + 2.5)} {f(y - 15)} L{f(x + 2.5)} {f(y)} Z" fill="#f3d6a6"/>'
        x += 14
    return o + '</g>'


def pond(cx, cy, rx, ry, rng):
    o = f'<ellipse cx="{f(cx)}" cy="{f(cy + 3)}" rx="{f(rx + 6)}" ry="{f(ry + 5)}" fill="#6fae47"/>'
    o += f'<ellipse cx="{f(cx)}" cy="{f(cy)}" rx="{f(rx + 4)}" ry="{f(ry + 3)}" fill="#e3d19c"/>'
    o += f'<ellipse cx="{f(cx)}" cy="{f(cy)}" rx="{f(rx)}" ry="{f(ry)}" fill="url(#pond)"/>'
    o += (f'<path d="M{f(cx - rx * 0.6)} {f(cy - ry * 0.45)} Q{f(cx - rx * 0.2)} {f(cy - ry * 0.7)} '
          f'{f(cx + rx * 0.2)} {f(cy - ry * 0.55)}" stroke="#fff" stroke-width="2.5" fill="none" opacity="0.6" stroke-linecap="round"/>')
    for dx, dy, r in ((-0.45, 0.25, 7), (0.35, 0.3, 6), (0.55, -0.1, 5)):
        x, y = cx + dx * rx, cy + dy * ry
        o += (f'<path d="M{f(x)} {f(y)} L{f(x + r)} {f(y - 2)} A{r} {r * 0.6} 0 1 1 {f(x + r * 0.6)} {f(y + r * 0.45)} Z" '
              f'fill="#5cb33f" stroke="#3f8a34" stroke-width="1"/>')
    o += flower(cx - rx * 0.45 + 2, cy + ry * 0.25 - 1, "#ff9ac1", 0.9)
    for dx in (-1.02, 1.0):
        x = cx + dx * rx
        for k in range(3):
            xx = x + (k - 1) * 4
            o += (f'<path d="M{f(xx)} {f(cy + 4)} L{f(xx + (k - 1) * 2)} {f(cy - 16 - k * 2)}" stroke="#4f8a2a" stroke-width="1.6"/>'
                  f'<ellipse cx="{f(xx + (k - 1) * 2)}" cy="{f(cy - 16 - k * 2)}" rx="2" ry="4.5" fill="#8a5a30"/>')
    return o


def butterfly(x, y, col):
    return (f'<g transform="translate({f(x)} {f(y)}) rotate(-15)">'
            f'<ellipse cx="-4" cy="-2" rx="4" ry="5" fill="{col}" stroke="{shade(col, 0.6)}" stroke-width="0.8"/>'
            f'<ellipse cx="4" cy="-2" rx="4" ry="5" fill="{col}" stroke="{shade(col, 0.6)}" stroke-width="0.8"/>'
            f'<ellipse cx="-3" cy="3" rx="2.5" ry="3" fill="{shade(col, 1.2)}"/>'
            f'<ellipse cx="3" cy="3" rx="2.5" ry="3" fill="{shade(col, 1.2)}"/>'
            f'<rect x="-0.8" y="-5" width="1.6" height="10" rx="0.8" fill="#3a2a1a"/></g>')


def cloud(cx, cy, s, op=1.0):
    puffs = ((-0.95, 0.15, 0.55), (-0.4, -0.25, 0.72), (0.35, -0.32, 0.66), (0.95, 0.08, 0.55), (0, 0.18, 0.78))
    o = f'<g opacity="{op}">'
    o += "".join(f'<circle cx="{f(cx + dx * s + 4)}" cy="{f(cy + dy * s + 8)}" r="{f(r * s)}" fill="#7d93b0" opacity="0.25" filter="url(#blur4)"/>' for dx, dy, r in puffs)
    o += "".join(f'<circle cx="{f(cx + dx * s)}" cy="{f(cy + dy * s)}" r="{f(r * s + 1.5)}" fill="#b9c7da"/>' for dx, dy, r in puffs)
    o += "".join(f'<circle cx="{f(cx + dx * s)}" cy="{f(cy + dy * s)}" r="{f(r * s)}" fill="url(#cloud)"/>' for dx, dy, r in puffs)
    return o + '</g>'


def road():
    d = pts_path(DENSE + [TRAIL_END], 3)
    return (f'<path d="{d}" fill="none" stroke="#1d4a12" stroke-opacity="0.18" stroke-width="40" '
            f'stroke-linecap="round" stroke-linejoin="round" filter="url(#blur4)" transform="translate(3 5)"/>'
            f'<path d="{d}" fill="none" stroke="#b98a4e" stroke-width="34" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="{d}" fill="none" stroke="#e9cc94" stroke-width="28" stroke-linecap="round" stroke-linejoin="round"/>'
            f'<path d="{d}" fill="none" stroke="#f3dcae" stroke-width="10" stroke-linecap="round" stroke-linejoin="round" opacity="0.7"/>')


def tile(x, y, state):
    """state: done / todo / here; камень-«таблетка» с боковиной."""
    top, side, rim = {"done": ("url(#gold)", "#c98a12", "#9c6a0c"),
                      "todo": ("url(#stone)", "#b9ae9a", "#8f8676"),
                      "here": ("url(#gold)", "#c98a12", "#9c6a0c")}[state]
    o = f'<ellipse cx="{f(x + 1)}" cy="{f(y + 7)}" rx="16" ry="8" fill="#5a3d16" opacity="0.25"/>'
    o += f'<ellipse cx="{f(x)}" cy="{f(y + 3)}" rx="15" ry="11" fill="{side}" stroke="{rim}" stroke-width="1.6"/>'
    o += f'<ellipse cx="{f(x)}" cy="{f(y - 1)}" rx="15" ry="11" fill="{top}" stroke="{rim}" stroke-width="1.6"/>'
    o += f'<ellipse cx="{f(x - 5)}" cy="{f(y - 5)}" rx="5" ry="2.4" fill="#fff" opacity="0.6"/>'
    if state == "done":
        o += star_path(x, y - 1, 5.2, "#fff8d6", "#c98a12")
    return o


def star_path(x, y, r, fill, stroke):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append(f"{f(x + math.cos(a) * rr)},{f(y + math.sin(a) * rr * 0.8)}")
    return f'<polygon points="{" ".join(pts)}" fill="{fill}" stroke="{stroke}" stroke-width="0.9" stroke-linejoin="round"/>'


def chest(x, y):
    o = shadow(x + 4, y + 2, 16, 5, 0.3)
    o += f'<rect x="{x - 13}" y="{y - 16}" width="26" height="16" rx="2" fill="#b0702f" stroke="#5e3a1e" stroke-width="1.6"/>'
    o += f'<path d="M{x - 13} {y - 16} Q{x} {y - 30} {x + 13} {y - 16} Z" fill="#c9843c" stroke="#5e3a1e" stroke-width="1.6"/>'
    o += f'<rect x="{x - 13}" y="{y - 18}" width="26" height="4" fill="#f5c04a" stroke="#8a5a14" stroke-width="1"/>'
    o += f'<rect x="{x - 3}" y="{y - 19}" width="6" height="8" rx="1" fill="#f5c04a" stroke="#8a5a14" stroke-width="1"/>'
    return o


def scene(zone_seed=0, step=9, n=25, hero_kind="fox"):
    rng = random.Random(zone_seed)
    defs = defs_common()
    o = f'<rect width="{W}" height="{H}" fill="url(#grass)"/>'
    # пятна света и тени на траве
    for _ in range(36):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        col = rng.choice(["#c8ec8a", "#7fbf4f"])
        o += f'<ellipse cx="{f(x)}" cy="{f(y)}" rx="{f(rng.uniform(25, 60))}" ry="{f(rng.uniform(10, 22))}" fill="{col}" opacity="0.35" filter="url(#blur8)"/>'
    for _ in range(260):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        if not _near_path(x, y, 22):
            o += tuft(x, y, rng.uniform(0.7, 1.2), rng.choice(["#5f9e3c", "#6aab44", "#a9d873"]))
    # клумбы-поля цветов
    for x0, y0, w, h, cols in ((300, 300, 130, 55, ("#ff6b8b", "#ffd23f")), (515, 160, 110, 50, ("#b48cff", "#ffffff"))):
        for i in range(70):
            x, y = x0 + rng.uniform(0, w), y0 + rng.uniform(0, h)
            if not _near_path(x, y, 20):
                o += flower(x, y, rng.choice(cols), rng.uniform(0.7, 1.0))
    o += road()

    objs = []   # (y, svg) — сортируем по y, ближние поверх
    objs.append((198, pond(395, 198, 78, 26, rng)))
    objs.append((100, house(205, 100, 1.05)))
    objs.append((103, fence(250, 330, 103)))
    objs.append((370, windmill(618, 370, 1.0)))
    for x, y, s in ((48, 95, 1.0), (108, 70, 0.85), (360, 72, 0.8), (455, 98, 1.0), (560, 80, 0.9),
                    (150, 238, 0.95), (245, 232, 0.85), (628, 236, 0.9), (95, 368, 0.95), (215, 372, 0.85),
                    (500, 372, 0.9)):
        objs.append((y, tree(x, y, s, rng.choice(["crown", "crown2"]))))
    objs.append((236, apple_tree(540, 238, 0.95, rng)))
    for x, y, s, b in ((300, 236, 0.8, True), (680, 236, 0.75, False), (25, 238, 0.7, False), (420, 102, 0.7, True),
                       (285, 372, 0.7, False), (720, 368, 0.7, True), (160, 102, 0.6, False), (790, 300, 0.7, False)):
        objs.append((y, bush(x, y, s, b, rng)))
    for _ in range(40):
        x, y = rng.uniform(5, W - 5), rng.choice([rng.uniform(418, 448), rng.uniform(5, 100), rng.uniform(150, 240),
                                                    rng.uniform(285, 372)])
        if not _near_path(x, y, 24) and not (x > 640 and y < 210):
            objs.append((y, flower(x, y, rng.choice(["#ff6b8b", "#ffd23f", "#ffffff", "#b48cff", "#ff9a3c"]), 0.85)))
    for y, s in sorted(objs, key=lambda t: t[0]):
        o += s

    # плитки
    pts = path_points(n)
    for i, (x, y) in enumerate(pts):
        o += tile(x, y, "done" if i < step else ("here" if i == step else "todo"))
    o += chest(*pts[-1]) if False else ""
    # бабочки
    for x, y, c in ((335, 175, "#ffd23f"), (470, 300, "#ff8fb1"), (90, 300, "#9fd4ff")):
        o += butterfly(x, y, c)
    o += f'<rect width="{W}" height="{H}" fill="url(#vign)"/>'
    # облака над следующей зоной
    o += f'<ellipse cx="760" cy="120" rx="90" ry="70" fill="#1d3d6b" opacity="0.18" filter="url(#blur8)"/>'
    for cx, cy, s in ((660, 22, 34), (795, 25, 72), (712, 58, 48), (778, 140, 62), (705, 165, 38), (800, 190, 40)):
        o += cloud(cx, cy, s)
    o += ('<g><circle cx="768" cy="128" r="21" fill="#ffffff" stroke="#b9c7da" stroke-width="2"/>'
          '<text x="768" y="140" font-family="DejaVu Sans" font-weight="bold" font-size="32" fill="#8aa0bf" '
          'text-anchor="middle">?</text></g>')
    # фигурка на текущей плите
    hx, hy = pts[step]
    o += f'<ellipse cx="{f(hx)}" cy="{f(hy)}" rx="30" ry="22" fill="url(#glow)"/>'
    d, g = hero(hero_kind, hx, hy + 3, 1.0)
    defs += d
    o += g
    return svg_doc(o, defs)


if __name__ == "__main__":
    render(scene(), "A_soft.png")
    render(scene(), "A_soft_2x.png", zoom=2)

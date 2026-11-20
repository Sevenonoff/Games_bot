"""Общее для пробных стилей: геометрия тропинки из проекта, SVG-хелперы, рендер."""
import math
import random
import sys
from pathlib import Path

sys.path.insert(0, "/home/clawuser/projects/Games_bot")
from games_core.journey_art import DENSE, TRAIL_END, path_points, _near_path  # noqa: E402

import resvg_py  # noqa: E402

FONT = "/home/clawuser/projects/Games_bot/games_core/art/DejaVuSans-Bold.ttf"
OUT = Path(__file__).with_name("out")
OUT.mkdir(exist_ok=True)
W, H = 800, 450


def f(v):
    return f"{v:.1f}".rstrip("0").rstrip(".")


def pts_path(pts, step=3):
    p = pts[::step] + [pts[-1]]
    return "M" + " L".join(f"{f(x)} {f(y)}" for x, y in p)


def render(svg, name, w=W, h=H, zoom=1):
    png = resvg_py.svg_to_bytes(svg_string=svg, font_files=[FONT], skip_system_fonts=True,
                                width=int(w * zoom), height=int(h * zoom))
    (OUT / name).write_bytes(bytes(png))
    return OUT / name


def svg_doc(body, defs="", w=W, h=H):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
            f'width="{w}" height="{h}" viewBox="0 0 {w} {h}"><defs>{defs}</defs>{body}</svg>')


def shade(hexc, k):
    """k<1 — темнее, k>1 — светлее (к белому)."""
    c = hexc.lstrip("#")
    r, g, b = (int(c[i:i + 2], 16) for i in (0, 2, 4))
    if k <= 1:
        r, g, b = (int(v * k) for v in (r, g, b))
    else:
        t = k - 1
        r, g, b = (int(v + (255 - v) * t) for v in (r, g, b))
    return f"#{r:02x}{g:02x}{b:02x}"

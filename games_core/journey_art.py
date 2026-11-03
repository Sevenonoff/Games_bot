"""Картинка «Пути»: фон зоны, тропинка из плит, фигурка и облака над следующей зоной.

Рисуется кодом при показе (Pillow) и кэшируется: каждую позицию фигурки рисовать заранее не нужно.
Фон зоны — плоские фигуры по теме зоны; свой фон — файл art/zone_<n>.png (тропинка и фигурка
рисуются поверх). Текста на картинке пути нет, подписи — в тексте сообщения.

Тропинка — змейка в три ряда снизу вверх, последняя плита — у облаков в правом верхнем углу.
Плит столько, сколько шагов в зоне; step — сколько пройдено, фигурка стоит на плите step.
"""
import io
import math
import random
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, List, Tuple

from PIL import Image, ImageDraw, ImageFont

W, H = 800, 450
SS = 2                      # рисуем вдвое крупнее и уменьшаем — края сглажены
ART_DIR = Path(__file__).with_name("art")
FONT_PATH = ART_DIR / "DejaVuSans-Bold.ttf"

ROWS_Y = (395, 262, 129)    # ряды змейки снизу вверх
ROW_X = ((50, 700), (700, 100), (100, 640))
TURN_R = (ROWS_Y[0] - ROWS_Y[1]) / 2
TRAIL_END = (775, 105)      # тропинка уходит в облака
CLOUD_BOX = (660, 0, 800, 200)
TILE_R = 16

Point = Tuple[float, float]
Color = Tuple[int, int, int]


def _hex(c: str) -> Color:
    c = c.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


# --- геометрия тропинки ---

def _dense_path() -> List[Point]:
    """Тропинка от первой до последней плиты, точки через ~1 px."""
    pts: List[Point] = []

    def line(a: Point, b: Point) -> None:
        n = max(2, int(math.dist(a, b)))
        pts.extend((a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n))

    def turn(cx: float, cy: float, right: bool) -> None:
        n = int(math.pi * TURN_R)
        for i in range(n):
            a = math.pi / 2 - math.pi * i / n       # снизу вверх
            dx = math.cos(a) * TURN_R
            pts.append((cx + dx if right else cx - dx, cy + math.sin(a) * TURN_R))

    line((ROW_X[0][0], ROWS_Y[0]), (ROW_X[0][1], ROWS_Y[0]))
    turn(ROW_X[0][1], (ROWS_Y[0] + ROWS_Y[1]) / 2, True)
    line((ROW_X[1][0], ROWS_Y[1]), (ROW_X[1][1], ROWS_Y[1]))
    turn(ROW_X[1][1], (ROWS_Y[1] + ROWS_Y[2]) / 2, False)
    line((ROW_X[2][0], ROWS_Y[2]), (ROW_X[2][1], ROWS_Y[2]))
    pts.append((ROW_X[2][1], ROWS_Y[2]))
    return pts


DENSE = _dense_path()


@lru_cache(maxsize=64)
def path_points(n: int) -> Tuple[Point, ...]:
    """Центры n плит, поровну по длине тропинки."""
    lengths = [0.0]
    for a, b in zip(DENSE, DENSE[1:]):
        lengths.append(lengths[-1] + math.dist(a, b))
    total, out, j = lengths[-1], [], 0
    for i in range(n):
        target = total * i / (n - 1) if n > 1 else 0
        while j < len(lengths) - 1 and lengths[j + 1] < target:
            j += 1
        out.append(DENSE[j])
    return tuple(out)


def _near_path(x: float, y: float, margin: float) -> bool:
    return any(abs(px - x) < margin and abs(py - y) < margin and math.hypot(px - x, py - y) < margin
               for px, py in DENSE[::6])


# --- рисование ---

class Canvas:
    """Координаты — в пикселях итоговой картинки 800×450, рисуем в SS раз крупнее."""

    def __init__(self, bg: Color):
        self.img = Image.new("RGB", (W * SS, H * SS), bg)
        self.d = ImageDraw.Draw(self.img, "RGBA")

    def _box(self, x0, y0, x1, y1):
        return [x0 * SS, y0 * SS, x1 * SS, y1 * SS]

    def ellipse(self, cx, cy, rx, ry, fill, outline=None, width=0):
        self.d.ellipse(self._box(cx - rx, cy - ry, cx + rx, cy + ry), fill=fill, outline=outline,
                       width=int(width * SS))

    def circle(self, cx, cy, r, fill, outline=None, width=0):
        self.ellipse(cx, cy, r, r, fill, outline, width)

    def rect(self, x0, y0, x1, y1, fill, radius=0, outline=None, width=0):
        self.d.rounded_rectangle(self._box(x0, y0, x1, y1), radius=radius * SS, fill=fill,
                                 outline=outline, width=int(width * SS))

    def poly(self, pts, fill, outline=None, width=0):
        self.d.polygon([(x * SS, y * SS) for x, y in pts], fill=fill, outline=outline,
                       width=int(width * SS) if outline else 0)

    def line(self, pts, fill, width):
        self.d.line([(x * SS, y * SS) for x, y in pts], fill=fill, width=int(width * SS), joint="curve")
        r = width / 2
        for x, y in (pts[0], pts[-1]):
            self.circle(x, y, r, fill)

    def text(self, cx, cy, s, size, fill, stroke=0, stroke_fill=None):
        font = ImageFont.truetype(str(FONT_PATH), int(size * SS))
        self.d.text((cx * SS, cy * SS), s, font=font, fill=fill, anchor="mm",
                    stroke_width=int(stroke * SS), stroke_fill=stroke_fill)

    def png(self, palette: bool = True) -> bytes:
        """palette — 256 цветов: картинка вдвое легче и кодируется втрое быстрее; для плоских
        фонов разницы не видно (открыткам с градиентом — полный цвет)."""
        out = io.BytesIO()
        img = self.img.resize((W, H), Image.LANCZOS)
        if palette:
            img = img.quantize(colors=256, method=Image.Quantize.MEDIANCUT)
        img.save(out, "PNG")
        return out.getvalue()


# --- украшения зон: (canvas, x, y, размер, rng) ---

Deco = Callable[[Canvas, float, float, float, random.Random], None]


def flower(c, x, y, s, rng):
    petal = rng.choice([_hex("#ff6b8b"), _hex("#ffd23f"), _hex("#ffffff"), _hex("#b48cff")])
    c.line([(x, y + s * 0.2), (x, y + s * 0.9)], _hex("#3d8b3d"), s * 0.12)
    for k in range(5):
        a = k * 2 * math.pi / 5
        c.circle(x + math.cos(a) * s * 0.28, y + math.sin(a) * s * 0.28, s * 0.22, petal)
    c.circle(x, y, s * 0.18, _hex("#f5a623"))


def bush(c, x, y, s, rng, color="#4f9d3a"):
    col = _hex(color)
    dark = tuple(int(v * 0.8) for v in col)
    c.ellipse(x, y + s * 0.55, s * 0.9, s * 0.2, (0, 0, 0, 40))
    for dx, dy, r in ((-0.45, 0.15, 0.45), (0.45, 0.15, 0.45), (0, -0.15, 0.55)):
        c.circle(x + dx * s, y + dy * s, r * s, dark)
    for dx, dy, r in ((-0.4, 0.05, 0.38), (0.4, 0.05, 0.38), (0, -0.22, 0.45)):
        c.circle(x + dx * s, y + dy * s, r * s, col)


def round_tree(c, x, y, s, rng, crown="#3f9a3a"):
    c.ellipse(x, y + s * 0.95, s * 0.6, s * 0.16, (0, 0, 0, 45))
    c.rect(x - s * 0.12, y + s * 0.2, x + s * 0.12, y + s * 0.95, _hex("#8b5a2b"), radius=2)
    col = _hex(crown)
    c.circle(x, y - s * 0.1, s * 0.62, tuple(int(v * 0.82) for v in col))
    c.circle(x - s * 0.08, y - s * 0.18, s * 0.5, col)


def pine(c, x, y, s, rng, color="#2f7d4a", snow=False):
    c.ellipse(x, y + s, s * 0.55, s * 0.15, (0, 0, 0, 45))
    c.rect(x - s * 0.1, y + s * 0.6, x + s * 0.1, y + s, _hex("#7a4b24"))
    col = _hex(color)
    for k, (top, w) in enumerate(((-1.0, 0.45), (-0.55, 0.6), (-0.1, 0.75))):
        tri = [(x, y + top * s), (x - w * s, y + (top + 0.75) * s), (x + w * s, y + (top + 0.75) * s)]
        c.poly(tri, tuple(int(v * (0.9 + 0.05 * k)) for v in col))
        if snow:
            c.poly([(x, y + top * s), (x - w * s * 0.4, y + (top + 0.3) * s),
                    (x + w * s * 0.4, y + (top + 0.3) * s)], _hex("#ffffff"))


def mushroom(c, x, y, s, rng):
    c.rect(x - s * 0.15, y, x + s * 0.15, y + s * 0.5, _hex("#f4ead5"), radius=3)
    c.d.chord(c._box(x - s * 0.5, y - s * 0.45, x + s * 0.5, y + s * 0.35), 180, 360, fill=_hex("#e2453c"))
    for dx, dy in ((-0.22, -0.12), (0.15, -0.2), (0.25, -0.02)):
        c.circle(x + dx * s, y + dy * s, s * 0.07, _hex("#ffffff"))


def rock(c, x, y, s, rng, color="#9a9a9a"):
    col = _hex(color)
    c.ellipse(x, y + s * 0.35, s * 0.6, s * 0.15, (0, 0, 0, 40))
    c.poly([(x - s * 0.55, y + s * 0.35), (x - s * 0.35, y - s * 0.2), (x + s * 0.1, y - s * 0.35),
            (x + s * 0.55, y + s * 0.35)], col)
    c.poly([(x - s * 0.35, y - s * 0.2), (x + s * 0.1, y - s * 0.35), (x, y + s * 0.05)],
           tuple(min(255, int(v * 1.15)) for v in col))


def mountain(c, x, y, s, rng):
    h, w = s * 1.6, s * 1.2
    c.poly([(x - w, y + s * 0.6), (x, y - h + s * 0.6), (x + w, y + s * 0.6)], _hex("#8a8f99"))
    c.poly([(x, y - h + s * 0.6), (x + w, y + s * 0.6), (x + w * 0.2, y + s * 0.6)], _hex("#737882"))
    c.poly([(x, y - h + s * 0.6), (x - w * 0.32, y - h * 0.62 + s * 0.6), (x - w * 0.1, y - h * 0.68 + s * 0.6),
            (x + w * 0.08, y - h * 0.58 + s * 0.6), (x + w * 0.3, y - h * 0.66 + s * 0.6)], _hex("#ffffff"))


def reeds(c, x, y, s, rng):
    for dx in (-0.25, 0, 0.25):
        c.line([(x + dx * s, y + s * 0.5), (x + dx * s * 1.4, y - s * 0.5)], _hex("#5c8a2e"), s * 0.08)
        c.ellipse(x + dx * s * 1.4, y - s * 0.45, s * 0.07, s * 0.18, _hex("#8b5a2b"))


def tower(c, x, y, s, rng):
    c.ellipse(x, y + s * 0.9, s * 0.6, s * 0.15, (0, 0, 0, 45))
    c.rect(x - s * 0.35, y - s * 0.4, x + s * 0.35, y + s * 0.9, _hex("#c9c1b0"))
    for k in range(3):
        c.rect(x - s * 0.35 + k * s * 0.28, y - s * 0.55, x - s * 0.2 + k * s * 0.28, y - s * 0.4, _hex("#c9c1b0"))
    c.d.chord(c._box(x - s * 0.13, y + s * 0.5, x + s * 0.13, y + s * 0.95), 180, 360, fill=_hex("#5a4632"))
    c.rect(x - s * 0.12, y + s * 0.72, x + s * 0.12, y + s * 0.9, _hex("#5a4632"))
    c.line([(x, y - s * 0.55), (x, y - s * 1.0)], _hex("#5a4632"), s * 0.05)
    c.poly([(x, y - s * 1.0), (x + s * 0.35, y - s * 0.9), (x, y - s * 0.8)], _hex("#e2453c"))


def castle(c, x, y, s, rng):
    wall = _hex("#d8d0bf")
    c.ellipse(x, y + s * 0.95, s * 1.5, s * 0.2, (0, 0, 0, 45))
    c.rect(x - s * 1.2, y - s * 0.1, x + s * 1.2, y + s * 0.95, wall)
    for k in range(7):
        c.rect(x - s * 1.2 + k * s * 0.37, y - s * 0.25, x - s * 1.0 + k * s * 0.37, y - s * 0.1, wall)
    for dx in (-1.25, 1.25):
        c.rect(x + dx * s - s * 0.3, y - s * 0.7, x + dx * s + s * 0.3, y + s * 0.95, _hex("#cbc2af"))
        c.poly([(x + dx * s - s * 0.38, y - s * 0.7), (x + dx * s, y - s * 1.3), (x + dx * s + s * 0.38, y - s * 0.7)],
               _hex("#4a6fd1"))
    c.rect(x - s * 0.35, y - s * 1.0, x + s * 0.35, y + s * 0.95, _hex("#e2dac9"))
    c.poly([(x - s * 0.45, y - s * 1.0), (x, y - s * 1.75), (x + s * 0.45, y - s * 1.0)], _hex("#d1453b"))
    c.line([(x, y - s * 1.75), (x, y - s * 2.05)], _hex("#5a4632"), s * 0.05)
    c.poly([(x, y - s * 2.05), (x + s * 0.4, y - s * 1.95), (x, y - s * 1.85)], _hex("#ffd23f"))
    c.d.chord(c._box(x - s * 0.22, y + s * 0.35, x + s * 0.22, y + s * 1.0), 180, 360, fill=_hex("#5a4632"))
    c.rect(x - s * 0.22, y + s * 0.67, x + s * 0.22, y + s * 0.95, _hex("#5a4632"))
    for dx in (-0.8, 0.8):
        c.rect(x + dx * s - s * 0.08, y + s * 0.2, x + dx * s + s * 0.08, y + s * 0.45, _hex("#5a4632"), radius=3)


def palm(c, x, y, s, rng):
    c.ellipse(x + s * 0.2, y + s * 1.0, s * 0.6, s * 0.15, (0, 0, 0, 40))
    c.line([(x, y + s), (x + s * 0.1, y + s * 0.3), (x + s * 0.25, y - s * 0.3)], _hex("#9c6b3a"), s * 0.16)
    top = (x + s * 0.25, y - s * 0.3)
    for a in (-160, -120, -60, -20, 20, 200):
        r = math.radians(a)
        tip = (top[0] + math.cos(r) * s * 0.8, top[1] + math.sin(r) * s * 0.5 + s * 0.15)
        mid = ((top[0] + tip[0]) / 2, (top[1] + tip[1]) / 2 - s * 0.12)
        c.poly([top, mid, tip, (mid[0], mid[1] + s * 0.14)], _hex("#2e9b4f"))
    c.circle(top[0] - s * 0.05, top[1] + s * 0.08, s * 0.1, _hex("#6b4423"))


def shell(c, x, y, s, rng):
    c.d.chord(c._box(x - s * 0.35, y - s * 0.3, x + s * 0.35, y + s * 0.4), 180, 360, fill=_hex("#ffb6a3"))
    for k in range(-2, 3):
        c.line([(x, y + s * 0.05), (x + k * s * 0.13, y - s * 0.25)], _hex("#e08a76"), s * 0.04)


def boat(c, x, y, s, rng):
    c.poly([(x - s * 0.6, y), (x + s * 0.6, y), (x + s * 0.4, y + s * 0.25), (x - s * 0.4, y + s * 0.25)],
           _hex("#8b5a2b"))
    c.line([(x, y), (x, y - s * 0.8)], _hex("#5a4632"), s * 0.05)
    c.poly([(x + s * 0.03, y - s * 0.78), (x + s * 0.5, y - s * 0.1), (x + s * 0.03, y - s * 0.1)], _hex("#ffffff"))


def cactus(c, x, y, s, rng):
    col = _hex("#3f9a52")
    c.ellipse(x, y + s * 0.9, s * 0.5, s * 0.13, (0, 0, 0, 40))
    c.rect(x - s * 0.15, y - s * 0.6, x + s * 0.15, y + s * 0.9, col, radius=s * 0.15)
    c.rect(x - s * 0.5, y - s * 0.1, x - s * 0.25, y + s * 0.35, col, radius=s * 0.12)
    c.rect(x - s * 0.5, y + s * 0.2, x - s * 0.1, y + s * 0.38, col, radius=s * 0.08)
    c.rect(x + s * 0.25, y - s * 0.35, x + s * 0.5, y + s * 0.15, col, radius=s * 0.12)
    c.rect(x + s * 0.1, y + s * 0.0, x + s * 0.5, y + s * 0.18, col, radius=s * 0.08)


def pyramid(c, x, y, s, rng):
    c.poly([(x - s * 1.1, y + s * 0.6), (x, y - s * 0.7), (x + s * 1.1, y + s * 0.6)], _hex("#d9a74f"))
    c.poly([(x, y - s * 0.7), (x + s * 1.1, y + s * 0.6), (x + s * 0.25, y + s * 0.6)], _hex("#bf8c3a"))


def dune(c, x, y, s, rng):
    c.d.chord(c._box(x - s * 1.2, y - s * 0.4, x + s * 1.2, y + s * 0.6), 180, 360, fill=_hex("#f2d48f"))


def ice(c, x, y, s, rng):
    c.ellipse(x, y + s * 0.55, s * 0.6, s * 0.14, (0, 0, 0, 30))
    for dx, h in ((-0.3, 0.7), (0.05, 1.1), (0.35, 0.6)):
        c.poly([(x + dx * s - s * 0.2, y + s * 0.55), (x + dx * s, y + s * 0.55 - h * s),
                (x + dx * s + s * 0.2, y + s * 0.55)], _hex("#9fd3f0"))
        c.poly([(x + dx * s, y + s * 0.55 - h * s), (x + dx * s + s * 0.2, y + s * 0.55),
                (x + dx * s + s * 0.05, y + s * 0.55)], _hex("#7bbde3"))


def snowman(c, x, y, s, rng):
    c.ellipse(x, y + s * 0.85, s * 0.5, s * 0.12, (0, 0, 0, 30))
    c.circle(x, y + s * 0.5, s * 0.4, _hex("#ffffff"), _hex("#c9dbe8"), 1.5)
    c.circle(x, y - s * 0.1, s * 0.28, _hex("#ffffff"), _hex("#c9dbe8"), 1.5)
    c.poly([(x, y - s * 0.1), (x + s * 0.3, y - s * 0.05), (x, y)], _hex("#f08a24"))
    for dx in (-0.1, 0.1):
        c.circle(x + dx * s, y - s * 0.18, s * 0.04, _hex("#333333"))


def building(c, x, y, s, rng):
    col = rng.choice([_hex("#e07a5f"), _hex("#81b29a"), _hex("#f2cc8f"), _hex("#7d8ccf"), _hex("#d4a5a5")])
    h = s * rng.uniform(1.0, 1.7)
    c.ellipse(x, y + s * 0.65, s * 0.7, s * 0.12, (0, 0, 0, 40))
    c.rect(x - s * 0.55, y + s * 0.65 - h, x + s * 0.55, y + s * 0.65, col)
    c.rect(x - s * 0.6, y + s * 0.65 - h - s * 0.08, x + s * 0.6, y + s * 0.65 - h, tuple(int(v * 0.8) for v in col))
    rows = max(1, int(h / (s * 0.35)))
    for r in range(rows):
        for k in (-1, 1):
            wy = y + s * 0.65 - h + s * 0.15 + r * s * 0.35
            if wy + s * 0.18 < y + s * 0.6:
                c.rect(x + k * s * 0.27 - s * 0.11, wy, x + k * s * 0.27 + s * 0.11, wy + s * 0.18, _hex("#fff3b0"))


def star(c, x, y, s, rng):
    r = s * rng.uniform(0.06, 0.16)
    c.circle(x, y, r, (255, 255, 230, rng.randint(150, 255)))


def planet(c, x, y, s, rng):
    col = rng.choice([_hex("#f2a65a"), _hex("#7fc8f8"), _hex("#e07ad8"), _hex("#9be564")])
    c.circle(x, y, s * 0.5, col)
    c.circle(x - s * 0.15, y - s * 0.15, s * 0.2, (255, 255, 255, 60))
    c.d.arc(c._box(x - s * 0.9, y - s * 0.25, x + s * 0.9, y + s * 0.25), 0, 180, fill=(255, 255, 255, 200),
            width=int(s * 0.08 * SS))


def rocket(c, x, y, s, rng):
    c.poly([(x, y - s * 0.8), (x + s * 0.25, y - s * 0.3), (x + s * 0.25, y + s * 0.4),
            (x - s * 0.25, y + s * 0.4), (x - s * 0.25, y - s * 0.3)], _hex("#eeeeee"))
    c.poly([(x, y - s * 0.8), (x + s * 0.25, y - s * 0.3), (x - s * 0.25, y - s * 0.3)], _hex("#e2453c"))
    c.circle(x, y - s * 0.1, s * 0.11, _hex("#4aa3df"))
    c.poly([(x - s * 0.25, y + s * 0.1), (x - s * 0.45, y + s * 0.5), (x - s * 0.25, y + s * 0.4)], _hex("#e2453c"))
    c.poly([(x + s * 0.25, y + s * 0.1), (x + s * 0.45, y + s * 0.5), (x + s * 0.25, y + s * 0.4)], _hex("#e2453c"))
    c.poly([(x - s * 0.15, y + s * 0.4), (x, y + s * 0.85), (x + s * 0.15, y + s * 0.4)], _hex("#ffb000"))


# --- темы зон ---

def _river(c: Canvas, rng: random.Random) -> None:
    pts = [(420 + math.sin(y / 70) * 35, y) for y in range(-10, H + 12, 6)]
    c.line(pts, _hex("#3b8fd0"), 74)
    c.line(pts, _hex("#4aa3df"), 60)
    for _ in range(26):
        y = rng.uniform(0, H)
        x = 420 + math.sin(y / 70) * 35 + rng.uniform(-18, 18)
        c.line([(x - 8, y), (x + 8, y)], (255, 255, 255, 120), 2)


def _sea(c: Canvas, rng: random.Random) -> None:
    for y0, y1 in ((-20, 78), (432, H + 20)):
        c.rect(-20, y0, W + 20, y1, _hex("#3fa7d6"))
    c.line([(x, 78 + math.sin(x / 18) * 4) for x in range(-10, W + 10, 4)], _hex("#fdf0c4"), 7)
    c.line([(x, 432 + math.sin(x / 18) * 4) for x in range(-10, W + 10, 4)], _hex("#fdf0c4"), 7)
    for _ in range(18):
        x, y = rng.uniform(0, 640), rng.choice([rng.uniform(10, 60), rng.uniform(440, 448)])
        c.d.arc(c._box(x - 8, y - 4, x + 8, y + 4), 200, 340, fill=(255, 255, 255, 170), width=2 * SS)
    for x in (120, 380, 560):
        boat(c, x + rng.uniform(-30, 30), 52, 22, rng)


def _mountains_back(c: Canvas, rng: random.Random) -> None:
    for x, s in ((150, 34), (300, 40), (470, 30), (600, 36)):
        mountain(c, x, 52, s, rng)


def _castle_feature(c: Canvas, rng: random.Random) -> None:
    castle(c, 330, 62, 26, rng)


def _city_grid(c: Canvas, rng: random.Random) -> None:
    for y in (64, 196, 329):
        c.rect(-10, y - 9, W + 10, y + 9, _hex("#a9a9ae"))
        for x in range(0, W, 40):
            c.rect(x, y - 1.5, x + 18, y + 1.5, _hex("#f2f2f2"))


def _stars(c: Canvas, rng: random.Random) -> None:
    for _ in range(220):
        star(c, rng.uniform(0, W), rng.uniform(0, H), 14, rng)


ZoneTheme = Dict[str, object]

THEMES: Tuple[ZoneTheme, ...] = (
    {"ground": "#9ed36a", "spot": "#8cc45a", "trail": "#d9c08a",
     "decos": ((flower, 18, 4), (bush, 22, 2), (round_tree, 27, 2))},
    {"ground": "#6aaa55", "spot": "#5c9a49", "trail": "#c7a774",
     "decos": ((pine, 30, 5), (round_tree, 27, 2), (mushroom, 16, 1), (bush, 19, 1))},
    {"ground": "#93d06c", "spot": "#83c05c", "trail": "#d8bf8b", "back": _river,
     "decos": ((reeds, 19, 2), (bush, 20, 2), (rock, 18, 1), (round_tree, 26, 1)), "avoid_river": True},
    {"ground": "#b9ad8f", "spot": "#a99d80", "trail": "#e0d2ae", "back": _mountains_back,
     "decos": ((rock, 20, 3), (pine, 24, 2), (mountain, 27, 1))},
    {"ground": "#a4d36d", "spot": "#94c35e", "trail": "#d6c9a8", "back": _castle_feature,
     "decos": ((tower, 24, 1), (round_tree, 24, 2), (flower, 15, 2), (bush, 19, 1))},
    {"ground": "#f1dc9c", "spot": "#e7cf8a", "trail": "#c9a76a", "back": _sea,
     "decos": ((palm, 30, 3), (shell, 14, 2), (rock, 16, 1))},
    {"ground": "#ebc97f", "spot": "#e0bb6c", "trail": "#c79a55",
     "decos": ((cactus, 24, 3), (dune, 30, 2), (pyramid, 30, 1), (rock, 15, 1))},
    {"ground": "#e6f3fb", "spot": "#d6e9f5", "trail": "#b5cfe2",
     "decos": ((ice, 24, 3), (lambda c, x, y, s, r: pine(c, x, y, s, r, "#3c7d68", snow=True), 27, 2),
               (snowman, 22, 1))},
    {"ground": "#cfd0d4", "spot": "#c3c4c9", "trail": "#9a9ba3", "back": _city_grid,
     "decos": ((building, 32, 4), (round_tree, 19, 1))},
    {"ground": "#1d1d40", "spot": "#26264f", "trail": "#4b4b86", "back": _stars,
     "decos": ((planet, 30, 2), (rocket, 30, 1), (star, 27, 3))},
)


def _in_river(x: float, y: float) -> bool:
    return abs(x - (420 + math.sin(y / 70) * 35)) < 52


def _in_cloud(x: float, y: float) -> bool:
    x0, y0, x1, y1 = CLOUD_BOX
    return x > x0 - 20 and y < y1 + 15


def _background(zone: int) -> Canvas:
    theme = THEMES[zone % len(THEMES)]
    rng = random.Random(f"zone-{zone}")
    custom = ART_DIR / f"zone_{zone}.png"
    c = Canvas(_hex(theme["ground"]))
    if custom.exists():
        c.img.paste(Image.open(custom).convert("RGB").resize((W * SS, H * SS), Image.LANCZOS))
        return c
    spot = _hex(theme["spot"])
    for _ in range(140):
        c.ellipse(rng.uniform(0, W), rng.uniform(0, H), rng.uniform(10, 34), rng.uniform(5, 14), spot)
    if "back" in theme:
        theme["back"](c, rng)
    # трасса под плитами
    trail = _hex(theme["trail"])
    c.line(DENSE[::3] + [TRAIL_END], tuple(int(v * 0.85) for v in trail), 26)
    c.line(DENSE[::3] + [TRAIL_END], trail, 20)
    # украшения на свободных местах
    choices = [(f, s) for f, s, w in theme["decos"] for _ in range(w)]
    spots = []
    for gy in range(14, H, 34):
        for gx in range(12, W, 38):
            x, y = gx + rng.uniform(-12, 12), gy + rng.uniform(-10, 10)
            spots.append((y, x))
    rng.shuffle(spots)
    placed = []
    for y, x in spots[: int(len(spots) * 0.55)]:
        f, s = rng.choice(choices)
        if _near_path(x, y, 26 + s * 0.5) or _in_cloud(x, y):
            continue
        if theme.get("avoid_river") and _in_river(x, y):
            continue
        if zone % len(THEMES) == 5 and (y < 92 or y > 422):
            continue
        if zone % len(THEMES) == 4 and 250 < x < 410 and y < 105:
            continue
        if any(math.hypot(x - px, y - py) < (s + ps) * 0.9 for px, py, ps, _ in placed):
            continue
        placed.append((x, y, s, f))
    for x, y, s, f in sorted(placed, key=lambda p: p[1]):   # дальние — раньше, ближние перекрывают
        f(c, x, y, s, rng)
    return c


def _tiles(c: Canvas, n: int, passed: int, trail: Color) -> None:
    for i, (x, y) in enumerate(path_points(n)):
        c.ellipse(x, y + 4, TILE_R + 1, TILE_R - 4, (0, 0, 0, 55))
        if i < passed:
            c.circle(x, y, TILE_R, _hex("#f6c343"), _hex("#b07d12"), 2.2)
            c.circle(x - 4, y - 5, TILE_R * 0.35, (255, 255, 255, 90))
        else:
            c.circle(x, y, TILE_R, _hex("#f3eee4"), _hex("#8f8676"), 2.2)
            c.circle(x - 4, y - 5, TILE_R * 0.3, (255, 255, 255, 120))


def _pawn(c: Canvas, x: float, y: float, k: float = 1.3) -> None:
    """Фигурка-пешка, стоящая на плите (x, y); k — масштаб."""
    out, body, lit = _hex("#2b2b2b"), _hex("#ffffff"), _hex("#e8eef7")
    w = 2.5
    c.ellipse(x, y + 2, 20 * k, 8 * k, (0, 0, 0, 70))
    c.circle(x, y, TILE_R + 5, (255, 236, 140, 110))
    c.ellipse(x, y - 4 * k, 17 * k, 7 * k, body, out, w)
    c.poly([(x - 14 * k, y - 6 * k), (x - 7 * k, y - 30 * k), (x + 7 * k, y - 30 * k), (x + 14 * k, y - 6 * k)],
           body, out, w)
    c.ellipse(x, y - 30 * k, 11 * k, 4.5 * k, lit, out, w)
    c.circle(x, y - 42 * k, 10.5 * k, body, out, w)
    c.circle(x - 3.5 * k, y - 45.5 * k, 3.5 * k, (255, 255, 255, 255))
    c.poly([(x - 12 * k, y - 7 * k), (x + 12 * k, y - 7 * k), (x + 13 * k, y - 4 * k), (x - 13 * k, y - 4 * k)], lit)


def _cloud(c: Canvas, cx: float, cy: float, s: float, alpha: int = 255) -> None:
    puffs = ((-0.9, 0.15, 0.55), (-0.35, -0.25, 0.7), (0.35, -0.3, 0.65), (0.9, 0.1, 0.55), (0, 0.2, 0.75))
    for dx, dy, r in puffs:
        c.circle(cx + dx * s, cy + dy * s + s * 0.12, r * s, (190, 200, 215, alpha))
    for dx, dy, r in puffs:
        c.circle(cx + dx * s, cy + dy * s, r * s, (255, 255, 255, alpha))


def _clouds(c: Canvas) -> None:
    # облака — только над концом верхнего ряда: правый поворот тропинки (y > 215) открыт
    for cx, cy, s in ((790, 30, 70), (705, 52, 46), (772, 140, 60), (718, 160, 36), (650, 18, 32)):
        _cloud(c, cx, cy, s)
    c.text(770, 132, "?", 54, _hex("#b5bfcc"))


def _finish(c: Canvas) -> None:
    """Пройденная зона: облаков нет, в конце тропинки — флаг."""
    x, y = TRAIL_END
    c.line([(x, y + 14), (x, y - 40)], _hex("#5a4632"), 4)
    c.poly([(x, y - 40), (x + 30, y - 31), (x, y - 22)], _hex("#e2453c"))
    c.ellipse(x, y + 14, 14, 5, (0, 0, 0, 60))


@lru_cache(maxsize=64)       # ~40 КБ на картинку: на сервере мало памяти
def render_zone(zone: int, step: int, size: int, mode: str = "current") -> bytes:
    """PNG пути.

    mode: current — фигурка на плите step, следующая зона за облаками;
          done    — пройденная зона: все плиты пройдены, фигурка у флага в конце;
          reveal  — зона только что открылась: облака расходятся, фигурка в начале.
    """
    c = _background(zone)
    trail = _hex(THEMES[zone % len(THEMES)]["trail"])
    if mode == "done":
        _tiles(c, size, size, trail)
        _finish(c)
        _pawn(c, TRAIL_END[0] - 18, TRAIL_END[1] + 12)
        return c.png()
    _tiles(c, size, step, trail)
    pts = path_points(size)
    _pawn(c, *pts[min(step, size - 1)])
    if mode == "reveal":
        for cx, cy, s, a in ((60, 40, 60, 150), (760, 60, 70, 130), (40, 300, 50, 110), (770, 400, 60, 120),
                             (420, -10, 55, 100)):
            _cloud(c, cx, cy, s, a)
        rng = random.Random(zone)
        for _ in range(26):
            x, y = rng.uniform(40, W - 40), rng.uniform(20, H - 20)
            c.poly([(x, y - 7), (x + 2, y - 2), (x + 7, y), (x + 2, y + 2), (x, y + 7), (x - 2, y + 2),
                    (x - 7, y), (x - 2, y - 2)], (255, 245, 170, 220))
    else:
        _clouds(c)
    return c.png()


# --- открытки за серию дней ---

CARD_THEMES = {
    "fire": ("#ff9a3c", "#ff4f5a"),
    "month": ("#8e5cff", "#ff5ca8"),
    "hundred": ("#ffcc33", "#ff7a00"),
}


def card_kind(days: int) -> str:
    if days >= 100 and days % 100 == 0:
        return "hundred"
    if days >= 30 and days % 30 == 0:
        return "month"
    return "fire"


def _flame(c: Canvas, x: float, y: float, s: float) -> None:
    """Пламя: капля с острым концом вверх, кончик чуть изогнут, по бокам — язычки."""
    def drop(cx, cy, r, color, bend=0.18):
        pts = []
        for i in range(80):
            a = 2 * math.pi * i / 80
            px = r * 0.8 * math.sin(a) * abs(math.sin(a / 2)) ** 1.3
            py = -r * 1.25 * math.cos(a)
            py = py * (1.25 if py < 0 else 0.75)                # вытянуть вверх, низ — круглее
            px += bend * r * max(0.0, -py / r) ** 2             # кончик клонится вбок
            pts.append((cx + px, cy + py))
        c.poly(pts, color)
    drop(x - s * 0.55, y + s * 0.25, s * 0.38, _hex("#ff5a1f"), -0.5)
    drop(x + s * 0.55, y + s * 0.3, s * 0.32, _hex("#ff5a1f"), 0.5)
    drop(x, y, s, _hex("#ff5a1f"))
    drop(x + s * 0.02, y + s * 0.28, s * 0.68, _hex("#ff9f1c"), 0.1)
    drop(x + s * 0.04, y + s * 0.52, s * 0.38, _hex("#ffe066"), 0.05)


@lru_cache(maxsize=8)
def render_card(days: int) -> bytes:
    top, bottom = (_hex(h) for h in CARD_THEMES[card_kind(days)])
    c = Canvas(top)
    for i in range(H):
        k = i / H
        col = tuple(int(top[j] + (bottom[j] - top[j]) * k) for j in range(3))
        c.rect(0, i, W, i + 1.5, col)
    rng = random.Random(days)
    for _ in range(60):
        x, y = rng.uniform(0, W), rng.uniform(0, H)
        col = rng.choice([(255, 255, 255, 150), (255, 240, 150, 200), (255, 200, 230, 170)])
        if rng.random() < 0.5:
            c.circle(x, y, rng.uniform(3, 7), col)
        else:
            c.rect(x, y, x + rng.uniform(6, 12), y + rng.uniform(3, 6), col, radius=1)
    c.rect(40, 30, W - 40, H - 30, (255, 255, 255, 40), radius=28, outline=(255, 255, 255, 160), width=4)
    _flame(c, 230, 245, 120)
    c.text(530, 190, str(days), 150 if days < 100 else 120, _hex("#ffffff"), 6, _hex("#b2302f"))
    word = "день" if days % 10 == 1 and days % 100 != 11 else (
        "дня" if 2 <= days % 10 <= 4 and not 12 <= days % 100 <= 14 else "дней")
    c.text(530, 315, f"{word} подряд!", 46, _hex("#ffffff"), 3, _hex("#b2302f"))
    return c.png(palette=False)

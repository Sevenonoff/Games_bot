"""Кадр пути из локации, нарисованной нейросетью: фон, монеты на тропе, сундук в конце, герой,
высокие предметы (мельница, дома, деревья) поверх монет и героя, которые стоят за ними. Зашедший за дом
герой виден полупрозрачным силуэтом.

Ассеты — art/journey/ (собирает art_work/chapter1/build.py): loc<N>/bg.jpg, after.jpg, occ_*.png, loc.json;
coin.png, chest.png, heroes/<герой>.png и <герой>_big.png.

Точки тропы: size + 1 точка по ломаной на равном расстоянии. Герой стоит на точке step, монеты лежат на
точках step+1 … size-1 (собранные исчезают), сундук — на последней точке, у облаков.
"""
import io
from functools import lru_cache
from typing import FrozenSet, List, Sequence, Tuple

from PIL import Image, ImageDraw, ImageFilter, ImageFont

from .locations import ROOT, Location, of_zone

W, H = 1280, 720
JPEG_QUALITY = 84
FONT_PATH = ROOT.parent / "DejaVuSans-Bold.ttf"
DEFAULT_HERO = "fox"

Point = Tuple[float, float]


MARGIN = (50, 60, 50, 30)     # слева, сверху, справа, снизу: герой у края кадра не обрезан


def _inside(p: Point) -> bool:
    x, y = p
    return MARGIN[0] <= x <= W - MARGIN[2] and MARGIN[1] <= y <= H - MARGIN[3]


def points(loc: Location, n: int) -> List[Point]:
    """n точек по тропе на равном расстоянии (в пикселях кадра); концы тропы за краем кадра отрезаны."""
    pts = [(x * W, y * H) for x, y in loc.path]
    inside = [i for i, p in enumerate(pts) if _inside(p)]
    if len(inside) >= 2:
        pts = pts[inside[0]:inside[-1] + 1]
    lengths = [0.0]
    for (x0, y0), (x1, y1) in zip(pts, pts[1:]):
        lengths.append(lengths[-1] + ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5)
    total, out, j = lengths[-1], [], 0
    for i in range(n):
        t = total * i / (n - 1) if n > 1 else 0.0
        while j < len(lengths) - 2 and lengths[j + 1] < t:
            j += 1
        seg = lengths[j + 1] - lengths[j] or 1.0
        u = min(1.0, max(0.0, (t - lengths[j]) / seg))
        (x0, y0), (x1, y1) = pts[j], pts[j + 1]
        out.append((x0 + (x1 - x0) * u, y0 + (y1 - y0) * u))
    return out


@lru_cache(maxsize=3)
def _background(loc_id: int, kind: str) -> Image.Image:
    loc = of_zone(loc_id - 1)
    path = loc.dir / f"{kind}.jpg"
    if not path.exists():
        path = loc.dir / "bg.jpg"
    return Image.open(path).convert("RGBA")


@lru_cache(maxsize=3)
def _layers(loc_id: int) -> Tuple[Tuple[Image.Image, int, int, int], ...]:
    loc = of_zone(loc_id - 1)
    return tuple((Image.open(loc.dir / l.file).convert("RGBA"), l.x, l.y, l.base) for l in loc.layers)


@lru_cache(maxsize=None)
def sprite(name: str) -> Image.Image:
    return Image.open(ROOT / f"{name}.png").convert("RGBA")


def _hero_key(hero: str) -> str:
    return hero if (ROOT / "heroes" / f"{hero}.png").exists() else DEFAULT_HERO


@lru_cache(maxsize=None)
def _shadow(w: int, h: int, alpha: int) -> Image.Image:
    im = Image.new("RGBA", (w * 2, h * 2), (0, 0, 0, 0))
    ImageDraw.Draw(im).ellipse((w / 2, h / 2, w * 1.5, h * 1.5), fill=(40, 30, 10, alpha))
    return im.filter(ImageFilter.GaussianBlur(max(1, h // 3)))


def _put_shadowed(canvas: Image.Image, im: Image.Image, cx: float, foot_y: float, shadow_w: float) -> None:
    """Спрайт стоит на точке (cx, foot_y): тень под ним, низ спрайта — на точке."""
    sh = _shadow(int(shadow_w), max(4, int(shadow_w * 0.32)), 95)
    canvas.alpha_composite(sh, (int(cx - sh.size[0] / 2), int(foot_y - sh.size[1] / 2)))
    canvas.alpha_composite(im, (int(cx - im.size[0] / 2), int(foot_y - im.size[1])))


def _hero(canvas: Image.Image, hero: str, x: float, y: float) -> None:
    im = sprite(f"heroes/{_hero_key(hero)}")
    hh = im.size[1]
    glow = Image.new("RGBA", (hh * 2, hh), (0, 0, 0, 0))
    ImageDraw.Draw(glow).ellipse((hh * 0.5, hh * 0.3, hh * 1.5, hh * 0.7), fill=(255, 236, 120, 130))
    canvas.alpha_composite(glow.filter(ImageFilter.GaussianBlur(hh * 0.07)), (int(x - hh), int(y - hh / 2)))
    _put_shadowed(canvas, im, x, y + hh * 0.04, hh * 0.55)


def _ghost(canvas: Image.Image, hero: str, x: float, y: float) -> None:
    """Полупрозрачный герой поверх всего: если он зашёл за дом, виден силуэтом; если не зашёл —
    ложится на самого себя и ничего не меняет."""
    im = sprite(f"heroes/{_hero_key(hero)}")
    ghost = im.copy()
    ghost.putalpha(im.getchannel("A").point(lambda a: a * 45 // 100))
    hh = im.size[1]
    canvas.alpha_composite(ghost, (int(x - im.size[0] / 2), int(y + hh * 0.04 - hh)))


def _sparkles(canvas: Image.Image, seed: int) -> None:
    """Блёстки — облака только что расступились."""
    import random
    rng = random.Random(seed)
    d = ImageDraw.Draw(canvas, "RGBA")
    for _ in range(36):
        x, y, r = rng.uniform(40, W - 40), rng.uniform(30, H - 30), rng.uniform(5, 11)
        d.polygon([(x, y - r), (x + r * 0.28, y - r * 0.28), (x + r, y), (x + r * 0.28, y + r * 0.28), (x, y + r),
                   (x - r * 0.28, y + r * 0.28), (x - r, y), (x - r * 0.28, y - r * 0.28)], fill=(255, 246, 180, 230))


def _jpeg(canvas: Image.Image) -> bytes:
    out = io.BytesIO()
    canvas.convert("RGB").save(out, "JPEG", quality=JPEG_QUALITY, optimize=True)
    return out.getvalue()


@lru_cache(maxsize=48)
def render(zone: int, step: int, size: int, mode: str = "current", hero: str = DEFAULT_HERO) -> bytes:
    """JPEG кадра. mode: current — герой на шаге step; reveal — то же, только что открылась (блёстки);
    done — пройденная локация: картинка «после», герой у сундука в конце."""
    loc = of_zone(zone)
    pts = points(loc, size + 1)
    if mode == "done":
        canvas = _background(loc.id, "after").copy()
        _hero(canvas, hero, *pts[-1])
        return _jpeg(canvas)
    canvas = _background(loc.id, "bg").copy()
    step = max(0, min(step, size - 1))
    items = []        # (y основания, порядок, рисование)
    coin, chest = sprite("coin"), sprite("chest")
    for i in range(step + 1, size):
        x, y = pts[i]
        items.append((y + coin.size[1] * 0.3, 1, lambda x=x, y=y: _put_shadowed(
            canvas, coin, x, y + coin.size[1] / 2, coin.size[0] * 1.05)))
    cx, cy = pts[size]
    items.append((cy + 6, 1, lambda: _put_shadowed(canvas, chest, cx, cy + chest.size[1] * 0.45, chest.size[0] * 1.1)))
    hx, hy = pts[step]
    items.append((hy, 2, lambda: _hero(canvas, hero, hx, hy)))
    for im, x, y, base in _layers(loc.id):
        items.append((base, 0, lambda im=im, x=x, y=y: canvas.alpha_composite(im, (x, y))))
    for _, _, draw in sorted(items, key=lambda t: (t[0], t[1])):
        draw()
    _ghost(canvas, hero, hx, hy)
    if mode == "reveal":
        _sparkles(canvas, zone)
    return _jpeg(canvas)


# --- экран «Герои» ---

def _font(size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_PATH), size)


def _lock(d: ImageDraw.ImageDraw, x: float, y: float) -> None:
    d.arc((x - 13, y - 30, x + 13, y - 4), 180, 360, fill=(245, 245, 250, 255), width=6)
    d.rounded_rectangle((x - 19, y - 14, x + 19, y + 16), radius=6, fill=(255, 201, 74, 255),
                        outline=(154, 106, 12, 255), width=3)
    d.ellipse((x - 4, y - 3, x + 4, y + 5), fill=(154, 106, 12, 255))


@lru_cache(maxsize=32)
def render_heroes(heroes: Tuple[Tuple[str, str, int], ...], owned: FrozenSet[str], selected: str) -> bytes:
    """Галерея героев: heroes — (ключ, имя, цена). Закрытые — силуэтом с замком и ценой."""
    loc = of_zone(0)
    if loc is not None:
        bg = _background(loc.id, "bg").copy().filter(ImageFilter.GaussianBlur(7))
    else:
        bg = Image.new("RGBA", (W, H), (150, 200, 120, 255))
    bg.alpha_composite(Image.new("RGBA", (W, H), (255, 255, 255, 70)))
    d = ImageDraw.Draw(bg, "RGBA")
    name_font, price_font = _font(30), _font(28)
    coin = sprite("coin").resize((34, round(sprite("coin").size[1] * 34 / sprite("coin").size[0])), Image.LANCZOS)
    cols, cell_w, cell_h = 4, W / 4, H / 2
    for i, (key, name, price) in enumerate(heroes):
        cx, top = cell_w * (i % cols) + cell_w / 2, cell_h * (i // cols)
        foot = top + cell_h - 78
        d.ellipse((cx - 92, foot - 20, cx + 92, foot + 20), fill=(255, 255, 255, 120))
        if key == selected:
            glow = Image.new("RGBA", (300, 120), (0, 0, 0, 0))
            ImageDraw.Draw(glow).ellipse((20, 20, 280, 100), fill=(255, 226, 90, 200))
            bg.alpha_composite(glow.filter(ImageFilter.GaussianBlur(14)), (int(cx - 150), int(foot - 60)))
        im = sprite(f"heroes/{_hero_key(key)}_big")
        scale = min(1.0, (cell_h - 110) / im.size[1])
        im = im.resize((round(im.size[0] * scale), round(im.size[1] * scale)), Image.LANCZOS)
        if key not in owned:
            sil = Image.new("RGBA", im.size, (52, 64, 88, 0))
            sil.putalpha(im.getchannel("A").point(lambda a: int(a * 0.82)))
            im = sil
        bg.alpha_composite(im, (int(cx - im.size[0] / 2), int(foot - im.size[1] + 10)))
        d.text((cx, foot + 42), name, font=name_font, fill=(255, 255, 255, 255), anchor="mm",
               stroke_width=4, stroke_fill=(40, 52, 30, 255))
        if key not in owned:
            _lock(d, cx, foot - im.size[1] * 0.55)
            label = str(price)
            tw = d.textlength(label, font=price_font)
            x0 = cx - (tw + coin.size[0] + 8) / 2
            bg.alpha_composite(coin, (int(x0), int(foot - im.size[1] * 0.55 + 30)))
            d.text((x0 + coin.size[0] + 8, foot - im.size[1] * 0.55 + 30 + coin.size[1] / 2), label, font=price_font,
                   fill=(255, 255, 255, 255), anchor="lm", stroke_width=4, stroke_fill=(110, 70, 10, 255))
    return _jpeg(bg)


def has_location(zone: int) -> bool:
    return of_zone(zone) is not None


def zone_points(zone: int, size: int) -> Sequence[Point]:
    return points(of_zone(zone), size + 1)

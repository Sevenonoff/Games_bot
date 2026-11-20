"""Сборка кадра пути из слоёв: чистый фон → (монеты, герой, высокие предметы) по глубине.

Высокие предметы (мельница и т. п.) вырезаются из исходной картинки по разнице с версией «без предмета»
и рисуются поверх монет, которые стоят дальше их основания.
"""
import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter
from skimage import filters, measure, morphology


def occluders(orig_path, clean_path, thr=40, min_area=300):
    """[(слой RGBA во весь кадр, y основания)] — по одному на каждый убранный предмет."""
    orig = Image.open(orig_path).convert("RGBA")
    a = np.asarray(orig.convert("RGB"), dtype=np.float32)
    b = np.asarray(Image.open(clean_path).convert("RGB"), dtype=np.float32)
    d = filters.gaussian(np.linalg.norm(a - b, axis=2), 2)
    m = morphology.closing(morphology.remove_small_objects(d > thr, min_area), morphology.disk(5))
    out = []
    lab = measure.label(m)
    for p in measure.regionprops(lab):
        if p.area < 2000:
            continue
        mask = morphology.dilation(lab == p.label, morphology.disk(2))
        alpha = Image.fromarray((mask * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.2))
        layer = orig.copy()
        layer.putalpha(alpha)
        out.append((layer, p.bbox[2] - 6))
    return out


def shadow(size, w, h, op=90):
    sh = Image.new("RGBA", size, (0, 0, 0, 0))
    ImageDraw.Draw(sh).ellipse((size[0] / 2 - w / 2, size[1] / 2 - h / 2, size[0] / 2 + w / 2, size[1] / 2 + h / 2),
                               fill=(40, 30, 10, op))
    return sh.filter(ImageFilter.GaussianBlur(h / 3))


def compose(clean_path, points_path, coin_path, hero_path, step, out_path, occ=(), hero_h=0.15, coin_w=0.034):
    bg = Image.open(clean_path).convert("RGBA")
    W, H = bg.size
    pts = [(x * W, y * H) for x, y in json.loads(Path(points_path).read_text())["points"]]
    coin = Image.open(coin_path).convert("RGBA")
    cw = int(W * coin_w)
    coin = coin.resize((cw, int(coin.size[1] * cw / coin.size[0])), Image.LANCZOS)
    hero = Image.open(hero_path).convert("RGBA")
    hh = int(H * hero_h)
    hero = hero.resize((int(hero.size[0] * hh / hero.size[1]), hh), Image.LANCZOS)

    items = []   # (y основания, функция рисования)
    for i, (x, y) in enumerate(pts):
        if i <= step:
            continue      # собранные монеты исчезают, на текущей плите стоит герой

        def draw_coin(c=bg, x=x, y=y):
            s = shadow((cw * 2, cw), cw * 1.1, cw * 0.38, 80)
            c.alpha_composite(s, (int(x - cw), int(y - cw / 2 + cw * 0.18)))
            c.alpha_composite(coin, (int(x - cw / 2), int(y - coin.size[1] / 2)))
        items.append((y + coin.size[1] * 0.3, draw_coin))
    hx, hy = pts[step]

    def draw_hero(c=bg):
        glow = Image.new("RGBA", (hh * 2, hh), (0, 0, 0, 0))
        ImageDraw.Draw(glow).ellipse((hh * 0.45, hh * 0.25, hh * 1.55, hh * 0.75), fill=(255, 236, 120, 120))
        c.alpha_composite(glow.filter(ImageFilter.GaussianBlur(hh * 0.08)), (int(hx - hh), int(hy - hh / 2)))
        s = shadow((hh, hh // 2), hh * 0.55, hh * 0.16, 110)
        c.alpha_composite(s, (int(hx - hh / 2), int(hy - hh / 4 + hh * 0.02)))
        c.alpha_composite(hero, (int(hx - hero.size[0] / 2), int(hy - hero.size[1] + hh * 0.05)))
    items.append((hy, draw_hero))
    for layer, base in occ:
        items.append((base, lambda c=bg, l=layer: c.alpha_composite(l)))
    for _, fn in sorted(items, key=lambda t: t[0]):
        fn()
    bg.convert("RGB").save(out_path, quality=88)
    return out_path

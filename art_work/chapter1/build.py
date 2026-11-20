"""Собирает ассеты главы для бота: games_core/art/journey/.

Для каждой локации: bg.jpg (оригинал), after.jpg («после»), слои высоких предметов (вырезаны по разнице
оригинала и «чистой» версии), тропа (по «чистой» версии) — всё в loc.json.
Общие спрайты: монета, сундук, герои.

python build.py [ids...]
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter
from skimage import filters, measure, morphology

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "gen"))
import trace as tr  # noqa: E402
from spec import CHAPTER, LOCATIONS  # noqa: E402

OUT = HERE.parents[1] / "games_core" / "art" / "journey"
W, H = 1280, 720
EMOJI = {1: "🏡", 2: "🎃", 3: "🍎", 4: "🏘", 5: "🎡", 6: "💧", 7: "🪁", 8: "🗼"}
HEROES = ("fox", "cat", "bear", "bunny", "penguin", "owl", "dino", "robot")
HERO_H = 112           # высота героя на кадре 1280×720
COIN_W = 44
CHEST_W = 78


def path_polyline(clean: Image.Image, n=80):
    """Плотная ломаная тропы в долях 0..1 от левого низа к правому верху."""
    W0, H0 = clean.size
    small = clean.convert("RGB").resize((480, round(480 * H0 / W0)), Image.LANCZOS)
    w, h = small.size
    m = tr.path_mask(small)
    yx = tr.longest_path(morphology.skeletonize(m))
    xy = [(x / w, y / h) for y, x in yx]
    if xy[0][0] - xy[0][1] > xy[-1][0] - xy[-1][1]:
        xy.reverse()
    arr = np.asarray(xy)
    k = 9
    pad = np.pad(arr, ((k, k), (0, 0)), mode="edge")
    ker = np.ones(2 * k + 1) / (2 * k + 1)
    arr = np.stack([np.convolve(pad[:, 0], ker, "valid"), np.convolve(pad[:, 1], ker, "valid")], axis=1)
    asp = np.array([W0 / H0, 1.0])
    pts = tr.resample(arr * asp, n) / asp
    return [[round(float(x), 4), round(float(y), 4)] for x, y in pts], m


def manual_polyline(anchors, n=80):
    """Ломаная по точкам, поставленным вручную (в процентах кадра), сглаженная."""
    a = np.asarray(anchors, dtype=float) / 100.0
    asp = np.array([W / H, 1.0])
    dense = tr.resample(a * asp, 400)
    k = 7
    pad = np.pad(dense, ((k, k), (0, 0)), mode="edge")
    ker = np.ones(2 * k + 1) / (2 * k + 1)
    dense = np.stack([np.convolve(pad[:, 0], ker, "valid"), np.convolve(pad[:, 1], ker, "valid")], axis=1)
    pts = tr.resample(dense, n) / asp
    return [[round(float(x), 4), round(float(y), 4)] for x, y in pts]


def occluder_layers(orig: Image.Image, clean: Image.Image, n: int, sandy: np.ndarray):
    """Слои предметов: [(png-имя, x, y, основание)] в координатах W×H. Пропускаем «шум» на самой тропе."""
    o = orig.convert("RGB").resize((W, H), Image.LANCZOS)
    c = clean.convert("RGB").resize((W, H), Image.LANCZOS)
    a, b = np.asarray(o, dtype=np.float32), np.asarray(c, dtype=np.float32)
    d = filters.gaussian(np.linalg.norm(a - b, axis=2), 2)
    m = morphology.closing(morphology.remove_small_objects(d > 38, max_size=400), morphology.disk(5))
    # песок тропы — по оригиналу: «чистая» версия могла расширить дорогу на месте убранного дома
    hsv = np.asarray(o.convert("HSV"), dtype=np.float32) / 255.0
    hh, ss, vv = hsv[..., 0] * 360, hsv[..., 1], hsv[..., 2]
    sandy_big = (hh > 22) & (hh < 48) & (ss > 0.22) & (ss < 0.62) & (vv > 0.68) & (a[..., 0] > a[..., 1]) & (
        a[..., 1] > a[..., 2]) & (a[..., 0] - a[..., 2] > 45)
    lab = measure.label(m)
    out = []
    rgba = o.convert("RGBA")
    for p in measure.regionprops(lab):
        if p.area < 900 or p.area > W * H * 0.2:
            continue
        region = lab == p.label
        # область, которая в оригинале — почти вся тропа, это не предмет, а перерисовка дороги
        if (sandy_big & region).sum() / p.area > 0.55:
            continue
        mask = morphology.dilation(region, morphology.disk(2))
        y0, x0, y1, x1 = p.bbox
        y0, x0, y1, x1 = max(0, y0 - 4), max(0, x0 - 4), min(H, y1 + 4), min(W, x1 + 4)
        alpha = Image.fromarray((mask[y0:y1, x0:x1] * 255).astype(np.uint8)).filter(ImageFilter.GaussianBlur(1.0))
        layer = rgba.crop((x0, y0, x1, y1))
        layer.putalpha(alpha)
        name = f"occ_{len(out) + 1}.webp"
        layer.save(OUT / f"loc{n}" / name, "WEBP", quality=88, method=6)
        out.append({"file": name, "x": x0, "y": y0, "base": int(p.bbox[2] - 5)})
    return out


def build_location(loc):
    n = loc["id"]
    src = HERE / f"loc{n}"
    (OUT / f"loc{n}").mkdir(parents=True, exist_ok=True)
    orig, clean = Image.open(src / "orig.png"), Image.open(src / "clean.png")
    orig.convert("RGB").resize((W, H), Image.LANCZOS).save(OUT / f"loc{n}" / "bg.jpg", quality=86, optimize=True)
    if (src / "after.png").exists():
        Image.open(src / "after.png").convert("RGB").resize((W, H), Image.LANCZOS).save(
            OUT / f"loc{n}" / "after.jpg", quality=86, optimize=True)
    poly, sandy = path_polyline(clean)
    manual = json.loads((HERE / "manual_paths.json").read_text())
    if str(n) in manual:
        poly = manual_polyline(manual[str(n)])
    layers = occluder_layers(orig, clean, n, sandy)
    meta = {"id": n, "chapter": CHAPTER["id"], "chapter_title": CHAPTER["title"], "emoji": EMOJI[n],
            "name": loc["name"], "intro": loc["intro"], "finish": loc["finish"], "path": poly, "layers": layers}
    (OUT / f"loc{n}" / "loc.json").write_text(json.dumps(meta, ensure_ascii=False, indent=1))
    print(n, loc["name"], "layers:", len(layers), "start", poly[0], "end", poly[-1])


def build_sprites():
    g = HERE.parent / "gen" / "out"
    (OUT / "heroes").mkdir(parents=True, exist_ok=True)

    def fit(im, w=None, h=None):
        im = im.crop(im.getbbox())
        if w:
            return im.resize((w, round(im.size[1] * w / im.size[0])), Image.LANCZOS)
        return im.resize((round(im.size[0] * h / im.size[1]), h), Image.LANCZOS)
    fit(Image.open(g / "coin_1.png"), w=COIN_W).save(OUT / "coin.png", optimize=True)
    fit(Image.open(g / "coin_4.png"), w=CHEST_W).save(OUT / "chest.png", optimize=True)
    for i, kind in enumerate(HEROES, 1):
        im = Image.open(g / f"hero_{i}.png")
        fit(im, h=HERO_H).save(OUT / "heroes" / f"{kind}.png", optimize=True)
        fit(im, h=200).save(OUT / "heroes" / f"{kind}_big.png", optimize=True)


if __name__ == "__main__":
    ids = [int(x) for x in sys.argv[1:]]
    OUT.mkdir(parents=True, exist_ok=True)
    build_sprites()
    for loc in LOCATIONS:
        if not ids or loc["id"] in ids:
            build_location(loc)

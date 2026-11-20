"""Вырезает спрайты с однотонного (пурпурного) фона: прозрачность, чистка ореола, по одному файлу на предмет.

python sprites.py <sheet.png> <prefix> [min_area]
"""
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from skimage import measure, morphology


def cut(sheet, prefix, min_area=1500):
    img = np.asarray(Image.open(sheet).convert("RGB")).astype(np.float32)
    h, w, _ = img.shape
    border = np.concatenate([img[:4].reshape(-1, 3), img[-4:].reshape(-1, 3), img[:, :4].reshape(-1, 3),
                             img[:, -4:].reshape(-1, 3)])
    bg = np.median(border, axis=0)
    d = np.linalg.norm(img - bg, axis=2)
    # «пурпурность» пикселя: и R, и B заметно выше G — так ловим и полупрозрачный ореол
    mag = np.clip(((img[..., 0] + img[..., 2]) / 2 - img[..., 1]) / max(1.0, ((bg[0] + bg[2]) / 2 - bg[1])), 0, 1)
    alpha = np.clip((d - 40) / 90, 0, 1)
    alpha = np.minimum(alpha, 1 - np.clip((mag - 0.55) / 0.35, 0, 1) * (d < 170))
    fg = alpha > 0.5
    fg = morphology.remove_small_objects(fg, 200)
    fg = morphology.closing(fg, morphology.disk(3))
    lab = measure.label(morphology.dilation(fg, morphology.disk(6)))
    # убираем пурпурный оттенок с краёв: вычитаем вклад фона
    a3 = np.clip(alpha, 0.05, 1)[..., None]
    rgb = np.clip((img - bg * (1 - a3)) / a3, 0, 255)
    rgb = np.where(alpha[..., None] > 0.98, img, rgb)
    out = []
    props = [p for p in measure.regionprops(lab) if p.area >= min_area]
    rows = sorted(props, key=lambda p: p.centroid[0])
    # группируем в ряды по вертикали
    groups, cur = [], []
    for p in rows:
        if cur and abs(p.centroid[0] - np.mean([q.centroid[0] for q in cur])) > h * 0.15:
            groups.append(cur)
            cur = []
        cur.append(p)
    if cur:
        groups.append(cur)
    n = 0
    for g in groups:
        for p in sorted(g, key=lambda p: p.centroid[1]):
            y0, x0, y1, x1 = p.bbox
            pad = 4
            y0, x0, y1, x1 = max(0, y0 - pad), max(0, x0 - pad), min(h, y1 + pad), min(w, x1 + pad)
            m = (lab[y0:y1, x0:x1] == p.label)
            a = (alpha[y0:y1, x0:x1] * m * 255).astype(np.uint8)
            rgba = np.dstack([rgb[y0:y1, x0:x1].astype(np.uint8), a])
            n += 1
            path = Path(sheet).with_name(f"{prefix}_{n}.png")
            Image.fromarray(rgba, "RGBA").save(path)
            out.append((path.name, x1 - x0, y1 - y0))
    return out


if __name__ == "__main__":
    for r in cut(sys.argv[1], sys.argv[2], int(sys.argv[3]) if len(sys.argv) > 3 else 1500):
        print(*r)

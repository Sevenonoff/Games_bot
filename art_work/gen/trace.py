"""Находит песчаную тропинку на фоне и раскладывает по ней N точек.

python trace.py <image> [N]  ->  печатает JSON {anchors, points} в долях 0..1, сохраняет out/mask_<name>.png
"""
import json
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image
from skimage import morphology, measure

WORK_W = 480


def path_mask(img):
    a = np.asarray(img.convert("HSV"), dtype=np.float32) / 255.0
    rgb = np.asarray(img.convert("RGB"), dtype=np.float32)
    h, s, v = a[..., 0] * 360, a[..., 1], a[..., 2]
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    m = (h > 22) & (h < 48) & (s > 0.22) & (s < 0.62) & (v > 0.68) & (r > g) & (g > b) & (r - b > 45)
    m = morphology.binary_opening(m, morphology.disk(2))
    m = morphology.binary_closing(m, morphology.disk(3))
    lab = measure.label(m)
    if lab.max() == 0:
        raise SystemExit("тропинка не найдена")
    big = max(measure.regionprops(lab), key=lambda p: p.area)
    return lab == big.label


def longest_path(skel):
    ys, xs = np.nonzero(skel)
    pts = set(zip(ys.tolist(), xs.tolist()))
    nb = [(-1, -1), (-1, 0), (-1, 1), (0, -1), (0, 1), (1, -1), (1, 0), (1, 1)]

    def bfs(start):
        dist, prev = {start: 0}, {start: None}
        q = deque([start])
        while q:
            p = q.popleft()
            for dy, dx in nb:
                n = (p[0] + dy, p[1] + dx)
                if n in pts and n not in dist:
                    dist[n] = dist[p] + 1
                    prev[n] = p
                    q.append(n)
        far = max(dist, key=dist.get)
        return far, prev

    a, _ = bfs(next(iter(pts)))
    b, prev = bfs(a)
    path, p = [], b
    while p is not None:
        path.append(p)
        p = prev[p]
    return path  # от b к a


def resample(pts, n):
    pts = np.asarray(pts, dtype=float)
    seg = np.hypot(*np.diff(pts, axis=0).T)
    L = np.concatenate([[0], np.cumsum(seg)])
    t = np.linspace(0, L[-1], n)
    return np.stack([np.interp(t, L, pts[:, 0]), np.interp(t, L, pts[:, 1])], axis=1)


def trace(path, n=25):
    img = Image.open(path).convert("RGB")
    W0, H0 = img.size
    small = img.resize((WORK_W, round(WORK_W * H0 / W0)), Image.LANCZOS)
    w, h = small.size
    m = path_mask(small)
    skel = morphology.skeletonize(m)
    yx = longest_path(skel)
    xy = [(x / w, y / h) for y, x in yx]
    # начало — то, что левее и ниже (у края картинки)
    if xy[0][0] - xy[0][1] > xy[-1][0] - xy[-1][1]:
        xy.reverse()
    # гладкость: сглаживаем скользящим средним
    arr = np.asarray(xy)
    k = 9
    if len(arr) > k * 2:
        pad = np.pad(arr, ((k, k), (0, 0)), mode="edge")
        ker = np.ones(2 * k + 1) / (2 * k + 1)
        arr = np.stack([np.convolve(pad[:, 0], ker, "valid"), np.convolve(pad[:, 1], ker, "valid")], axis=1)
    # длина в пикселях: x в долях × аспект
    asp = np.array([W0 / H0, 1.0])
    pts = resample(arr * asp, n) / asp
    anchors = resample(arr * asp, 16) / asp
    Image.fromarray((m * 255).astype("uint8")).save(Path(path).parent / f"mask_{Path(path).stem}.png")
    r4 = lambda a: [[round(float(x), 4), round(float(y), 4)] for x, y in a]
    return {"image": Path(path).name, "steps": n, "points": r4(pts), "anchors": r4(anchors)}


if __name__ == "__main__":
    print(json.dumps(trace(sys.argv[1], int(sys.argv[2]) if len(sys.argv) > 2 else 25)))

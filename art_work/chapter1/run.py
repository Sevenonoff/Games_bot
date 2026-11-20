"""Генерация главы 1: локации по очереди (образец — первая и предыдущая), по 3 варианта, выбор по тропе;
затем для каждой — «чистая» версия (без высоких предметов) и картинка «после».

python run.py scenes      — локация 1 (+улитка) и локации 2..8
python run.py edits       — clean + after для всех
python run.py pick N V    — вручную выбрать вариант V для локации N (копирует в orig.png)
"""
import base64
import io
import json
import sys
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "gen"))
import trace as tr  # noqa: E402
from spec import ADD_SNAIL_1, CLEAN_PROMPT, LOCATIONS, scene_prompt  # noqa: E402
from skimage import morphology  # noqa: E402

KEY = (HERE.parents[1] / ".cometapi_key").read_text().strip()
MODEL = "gemini-3-pro-image-preview"
URL = f"https://api.cometapi.com/v1beta/models/{MODEL}:generateContent"


def log(*a):
    print(time.strftime("%H:%M:%S"), *a, flush=True)


def ref_bytes(path, w=1376):
    im = Image.open(path).convert("RGB")
    im.thumbnail((w, w))
    buf = io.BytesIO()
    im.save(buf, "JPEG", quality=88)
    return buf.getvalue()


def gemini(prompt, refs, out, size="2K", tries=3):
    parts = [{"inline_data": {"mime_type": "image/jpeg", "data": base64.b64encode(ref_bytes(p)).decode()}} for p in refs]
    parts.append({"text": prompt})
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": {"responseModalities": ["IMAGE"],
                                 "imageConfig": {"aspectRatio": "16:9", "imageSize": size}}}
    for attempt in range(tries):
        try:
            req = urllib.request.Request(URL, data=json.dumps(body).encode(), method="POST",
                                         headers={"Content-Type": "application/json", "x-goog-api-key": KEY,
                                                  "Authorization": f"Bearer {KEY}"})
            with urllib.request.urlopen(req, timeout=400) as r:
                resp = json.loads(r.read())
            ps = [p for p in resp["candidates"][0]["content"]["parts"] if "inlineData" in p and not p.get("thought")]
            Path(out).parent.mkdir(parents=True, exist_ok=True)
            Path(out).write_bytes(base64.b64decode(ps[-1]["inlineData"]["data"]))
            log("saved", out)
            return out
        except Exception as e:  # noqa: BLE001
            msg = e.read()[:300] if hasattr(e, "read") else str(e)[:300]
            log("error", out, attempt, msg)
            time.sleep(5)
    return None


def path_score(path):
    """Насколько хороша тропа: длинная, одна, от левого низа к правому верху."""
    try:
        img = Image.open(path).convert("RGB")
        W0, H0 = img.size
        small = img.resize((480, round(480 * H0 / W0)), Image.LANCZOS)
        w, h = small.size
        m = tr.path_mask(small)
        sk = morphology.skeletonize(m)
        yx = tr.longest_path(sk)
        ys, xs = zip(*yx)
        # развилки: точки скелета с 3+ соседями
        p = np.pad(sk, 1).astype(int)
        nb = sum(np.roll(np.roll(p, dy, 0), dx, 1) for dy in (-1, 0, 1) for dx in (-1, 0, 1)) - p
        junctions = int(((nb[1:-1, 1:-1] >= 3) & sk).sum())
        a, b = (xs[0] / w, ys[0] / h), (xs[-1] / w, ys[-1] / h)
        start, end = (a, b) if a[0] - a[1] < b[0] - b[1] else (b, a)
        length = len(yx) / w
        sandy = m.sum() / (w * h)
        score = min(length, 3.2)
        score -= 0.6 * (start[0] > 0.2) + 0.6 * (start[1] < 0.7)
        score -= 0.6 * (end[0] < 0.55) + 0.6 * (end[1] > 0.45)
        score -= 0.04 * junctions
        return {"score": round(score, 2), "length": round(length, 2), "junctions": junctions,
                "start": [round(v, 2) for v in start], "end": [round(v, 2) for v in end], "sandy": round(float(sandy), 3)}
    except SystemExit as e:
        return {"score": -9, "error": str(e)}


def loc_dir(n):
    return HERE / f"loc{n}"


def one_location(loc):
    n, d = loc["id"], loc_dir(loc["id"])
    if (d / "orig.png").exists():
        return
    refs = []
    prompt = scene_prompt(loc)
    d.mkdir(exist_ok=True)
    (d / "prompt.txt").write_text(prompt)
    with ThreadPoolExecutor(3) as ex:
        outs = list(ex.map(lambda v: gemini(prompt, refs, d / f"v{v}.png"), (1, 2, 3)))
    scores = {Path(o).name: path_score(o) for o in outs if o}
    (d / "scores.json").write_text(json.dumps(scores, indent=1))
    log(n, scores)
    if not scores:
        log("no variants for", n)
        return
    best = max(scores, key=lambda k: scores[k]["score"])
    Image.open(d / best).save(d / "orig.png")
    (d / "picked.txt").write_text(best)
    log("picked", n, best)


def scenes(ids=None):
    """Локации не зависят друг от друга (образец стиля — фрагменты первой), поэтому идут параллельно."""
    d1 = loc_dir(1)
    if not (d1 / "orig.png").exists():
        gemini(ADD_SNAIL_1, [HERE.parent / "gen/out/gemini_2.png"], d1 / "orig.png")
    todo = [loc for loc in LOCATIONS[1:] if ids is None or loc["id"] in ids]
    with ThreadPoolExecutor(3) as ex:
        list(ex.map(one_location, todo))


def edits():
    jobs = []
    for loc in LOCATIONS:
        d = loc_dir(loc["id"])
        if not (d / "orig.png").exists():
            continue
        if not (d / "clean.png").exists():
            jobs.append((CLEAN_PROMPT, [d / "orig.png"], d / "clean.png"))
        if not (d / "after.png").exists():
            jobs.append((loc["after"], [d / "orig.png"], d / "after.png"))
    with ThreadPoolExecutor(4) as ex:
        list(ex.map(lambda j: gemini(*j), jobs))


if __name__ == "__main__":
    cmd = sys.argv[1]
    if cmd == "scenes":
        scenes([int(x) for x in sys.argv[2:]] or None)
    elif cmd == "edits":
        edits()
    elif cmd == "pick":
        n, v = sys.argv[2], sys.argv[3]
        Image.open(loc_dir(n) / f"v{v}.png").save(loc_dir(n) / "orig.png")
        (loc_dir(n) / "picked.txt").write_text(f"v{v}.png (manual)")

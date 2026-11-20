"""Фон от нейросети + плитки по точкам + герой: как будет выглядеть в боте.

python overlay.py <image.jpg> <points.json> <out.jpg> [step] [hero]
"""
import base64
import json
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "art"))
from common import f, render  # noqa: E402
from heroes import hero  # noqa: E402
from PIL import Image  # noqa: E402


def star(x, y, r, fill, stroke):
    pts = []
    for i in range(10):
        a = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append(f"{f(x + math.cos(a) * rr)},{f(y + math.sin(a) * rr * 0.8)}")
    return f'<polygon points="{" ".join(pts)}" fill="{fill}" stroke="{stroke}" stroke-width="1.2" stroke-linejoin="round"/>'


def tile(x, y, s, done):
    rx, ry = 15 * s, 11 * s
    top, side, rim = ("url(#gold)", "#c98a12", "#8a5e0a") if done else ("url(#stone)", "#b3a690", "#7d735f")
    o = f'<ellipse cx="{f(x + s)}" cy="{f(y + 7 * s)}" rx="{f(rx + s)}" ry="{f(ry * 0.75)}" fill="#3a2a10" opacity="0.3"/>'
    o += f'<ellipse cx="{f(x)}" cy="{f(y + 3.5 * s)}" rx="{f(rx)}" ry="{f(ry)}" fill="{side}" stroke="{rim}" stroke-width="{f(1.6 * s)}"/>'
    o += f'<ellipse cx="{f(x)}" cy="{f(y - s)}" rx="{f(rx)}" ry="{f(ry)}" fill="{top}" stroke="{rim}" stroke-width="{f(1.6 * s)}"/>'
    o += f'<ellipse cx="{f(x - 5 * s)}" cy="{f(y - 5 * s)}" rx="{f(5 * s)}" ry="{f(2.4 * s)}" fill="#fff" opacity="0.6"/>'
    if done:
        o += star(x, y - s, 5.2 * s, "#fff8d6", "#c98a12")
    return o


def main(img_path, pts_path, out, step=10, kind="fox"):
    img = Image.open(img_path)
    W, H = img.size
    b64 = base64.b64encode(Path(img_path).read_bytes()).decode()
    pts = [(x * W, y * H) for x, y in json.loads(Path(pts_path).read_text())["points"]]
    s = W / 800 * 0.95
    defs = ('<linearGradient id="stone" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#fbf8f1"/>'
            '<stop offset="1" stop-color="#d8cfbd"/></linearGradient>'
            '<linearGradient id="gold" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#ffe680"/>'
            '<stop offset="1" stop-color="#f5b324"/></linearGradient>'
            '<radialGradient id="glow"><stop offset="0" stop-color="#fff6b0" stop-opacity="0.95"/>'
            '<stop offset="0.55" stop-color="#ffe45c" stop-opacity="0.55"/>'
            '<stop offset="1" stop-color="#ffe45c" stop-opacity="0"/></radialGradient>')
    body = f'<image href="data:image/jpeg;base64,{b64}" x="0" y="0" width="{W}" height="{H}"/>'
    for i, (x, y) in enumerate(pts):
        body += tile(x, y, s, i < step)
    hx, hy = pts[step]
    body += f'<ellipse cx="{f(hx)}" cy="{f(hy)}" rx="{f(30 * s)}" ry="{f(22 * s)}" fill="url(#glow)"/>'
    d, g = hero(kind, hx, hy + 3 * s, 1.05 * s)
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" viewBox="0 0 {W} {H}">'
           f'<defs>{defs}{d}</defs>{body}{g}</svg>')
    p = render(svg, "tmp_overlay.png", W, H)
    Image.open(p).convert("RGB").save(out, quality=86)
    print("saved", out)


if __name__ == "__main__":
    a = sys.argv
    main(a[1], a[2], a[3], int(a[4]) if len(a) > 4 else 10, a[5] if len(a) > 5 else "fox")

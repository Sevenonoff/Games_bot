"""Стиль B «Пиксель-арт»: холст 200×112 px, увеличение ×4 без сглаживания, своя палитра."""
import math
import random
import sys

sys.path.insert(0, "/home/clawuser/projects/Games_bot")
from PIL import Image  # noqa: E402

from common import OUT, path_points, _near_path, DENSE, TRAIL_END  # noqa: E402

PW, PH, Z = 200, 113, 4

P = {
    ".": None,
    "k": (34, 32, 52),      # контур
    "g": (106, 190, 48),    # трава
    "G": (75, 160, 45),     # трава тёмная
    "h": (153, 229, 80),    # трава светлая
    "d": (55, 115, 50),     # листва тёмная
    "l": (106, 190, 48),
    "L": (153, 229, 80),
    "t": (143, 86, 59),     # ствол
    "T": (102, 57, 49),
    "s": (238, 195, 154),   # песок дороги
    "S": (217, 160, 102),
    "w": (255, 255, 255),
    "W": (203, 219, 252),
    "c": (155, 173, 183),   # облако тень
    "b": (91, 110, 225),    # вода
    "B": (99, 155, 255),
    "y": (251, 242, 54),
    "Y": (223, 113, 38),
    "r": (217, 87, 99),
    "R": (172, 50, 50),
    "p": (215, 123, 186),
    "o": (223, 113, 38),    # лиса
    "O": (255, 160, 70),
    "e": (238, 195, 154),
    "n": (69, 40, 60),
    "x": (132, 126, 135),   # камень
    "X": (105, 106, 106),
    "v": (118, 66, 138),
    "u": (95, 205, 228),
}


def sprite(rows):
    return [list(r) for r in rows]


FOX = sprite([
    "..k.......k....",
    ".kok.....kok...",
    ".knok...konk...",
    ".koookkkoook...",
    "kooooooooooook.",
    "kookoooookook..",
    "kookoooookook..",
    "kwwwwwkwwwwwk..",
    ".kwwwwwwwwwk...",
    "..kkoooooookk..",
    "...kowwwok..kk.",
    "..koowwwook.kwk",
    "..koowwwookkook",
    "..kooowoooooOk.",
    "...kooooooook..",
    "...knk...knk...",
])

TREE = sprite([
    "....kkkkk....",
    "..kkLLlllkk..",
    ".kLLLlllllGk.",
    ".kLlllllllGk.",
    "kLLllllllGGdk",
    "kLlllllllGGdk",
    "kllllllllGddk",
    ".klllllGGddk.",
    ".kGGlGGGdddk.",
    "..kkGddddkk..",
    "....ktTk.....",
    "....ktTk.....",
    "...kktTkk....",
])

BUSH = sprite([
    "..kkk.kkk..",
    ".kLllklllk.",
    "kLlllllllGk",
    "kllrlllrlGk",
    "kGlllllGGdk",
    ".kkkkkkkkk.",
])

HOUSE = sprite([
    "........kkk.......",
    "......kkRRkkkk....",
    ".....kRrrrkRRk....",
    "....kRrrrrrkRRk...",
    "...kRrrrrrrrkRRk..",
    "..kRrrrrrrrrrkRRk.",
    ".kRrrrrrrrrrrrkRRk",
    "kkkkkkkkkkkkkkkkkk",
    ".kwwwwwwwwwwwwWWk.",
    ".kwkkkwwwwwkkkWWk.",
    ".kwkukwkkkwkukWWk.",
    ".kwkkkwkTkwkkkWWk.",
    ".kwwwwwkTkwwwwWWk.",
    ".kwwwwwkTkwwwwWWk.",
    ".kkkkkkkkkkkkkkkk.",
])

FLOWER_R = sprite([".r.", "ryr", ".r.", ".G."])
FLOWER_W = sprite([".w.", "wyw", ".w.", ".G."])
FLOWER_P = sprite([".p.", "pyp", ".p.", ".G."])

TILE_TODO = sprite([
    ".kkkkk.",
    "kwwwwWk",
    "kwWWWxk",
    "kWWWxxk",
    ".kkkkk.",
])
TILE_DONE = sprite([
    ".kkkkk.",
    "kyywyYk",
    "kyyyyYk",
    "kYyyYYk",
    ".kkkkk.",
])

MILL = sprite([
    "k.....k.....k",
    ".kw...k...wk.",
    "..kw..k..wk..",
    "...kw.k.wk...",
    "....kkRkk....",
    "kkkkkRkRkkkkk",
    "....kkRkk....",
    "...kwkwkwk...",
    "...kwwwWWk...",
    "..kwwwwwWWk..",
    "..kwwkkwWWk..",
    "..kwwkTkWWk..",
    ".kwwwkTkwWWk.",
    ".kkkkkkkkkkk.",
])


class PixCanvas:
    def __init__(self):
        self.img = Image.new("RGB", (PW, PH), P["g"])
        self.px = self.img.load()

    def put(self, x, y, c):
        if 0 <= x < PW and 0 <= y < PH and c is not None:
            self.px[x, y] = c if isinstance(c, tuple) else P[c]

    def blit(self, spr, x, y):
        """(x, y) — середина нижнего края спрайта."""
        h, w = len(spr), max(len(r) for r in spr)
        x0, y0 = int(x - w // 2), int(y - h + 1)
        for j, row in enumerate(spr):
            for i, ch in enumerate(row):
                if ch != ".":
                    self.put(x0 + i, y0 + j, ch)

    def disc(self, cx, cy, rx, ry, c):
        for y in range(int(cy - ry) - 1, int(cy + ry) + 2):
            for x in range(int(cx - rx) - 1, int(cx + rx) + 2):
                if ((x - cx) / rx) ** 2 + ((y - cy) / ry) ** 2 <= 1:
                    self.put(x, y, c)


def scene(step=9, n=25, out="B_pixel.png"):
    rng = random.Random(3)
    c = PixCanvas()
    s = 4  # координаты пути делим на 4
    # текстура травы: дизеринг
    for y in range(PH):
        for x in range(PW):
            r = rng.random()
            if r < 0.06:
                c.put(x, y, "G")
            elif r < 0.09:
                c.put(x, y, "h")
    for _ in range(90):
        x, y = rng.randrange(PW), rng.randrange(PH)
        c.put(x, y, "G"); c.put(x + 1, y - 1, "G"); c.put(x + 2, y, "G")
    # пруд
    c.disc(99, 50, 21, 7.5, "k")
    c.disc(99, 50, 20, 6.5, "b")
    c.disc(98, 49, 16, 4.5, "B")
    for x in range(88, 96):
        c.put(x, 47, "w")
    # дорога
    pts = [(x / s, y / s) for x, y in DENSE[::2]] + [(TRAIL_END[0] / s, TRAIL_END[1] / s)]
    for x, y in pts:
        c.disc(x, y, 4.4, 4.4, "S")
    for x, y in pts:
        c.disc(x, y, 3.4, 3.4, "s")
    # камешки на обочине
    for x, y in pts[::9]:
        c.put(int(x + rng.choice([-5, 5])), int(y + rng.choice([-4, 4])), "x")
    objs = []
    objs.append((25, HOUSE, 51, 25))
    objs.append((92, MILL, 154, 92))
    for x, y in ((12, 24), (27, 18), (90, 18), (114, 24), (140, 20), (38, 59), (61, 58), (157, 59), (24, 92),
                 (54, 93), (125, 93)):
        objs.append((y, TREE, x, y))
    for x, y in ((75, 59), (170, 59), (105, 25), (72, 93), (180, 92)):
        objs.append((y, BUSH, x, y))
    for _ in range(70):
        x, y = rng.randrange(2, PW - 2), rng.choice([rng.randrange(2, 26), rng.randrange(38, 60), rng.randrange(72, 93),
                                                      rng.randrange(105, 113)])
        if not _near_path(x * s, y * s, 22) and not (x > 160 and y < 52) and not (76 < x < 122 and 40 < y < 58):
            objs.append((y, rng.choice([FLOWER_R, FLOWER_W, FLOWER_P, FLOWER_W]), x, y))
    for y, spr, x, yy in sorted(objs, key=lambda t: t[0]):
        c.blit(spr, x, yy)
    # плитки
    pp = path_points(n)
    for i, (x, y) in enumerate(pp):
        c.blit(TILE_DONE if i < step else TILE_TODO, round(x / s), round(y / s) + 2)
    # облака
    for cx, cy, rx, ry in ((200, 8, 26, 14), (178, 14, 14, 9), (194, 34, 18, 12), (176, 42, 10, 7), (198, 50, 12, 8),
                           (165, 5, 9, 6)):
        c.disc(cx, cy + 1, rx + 1, ry + 1, "k")
    for cx, cy, rx, ry in ((200, 8, 26, 14), (178, 14, 14, 9), (194, 34, 18, 12), (176, 42, 10, 7), (198, 50, 12, 8),
                           (165, 5, 9, 6)):
        c.disc(cx, cy + 1, rx, ry, "c")
        c.disc(cx - 1, cy - 1, rx - 1, ry - 1, "w")
    QM = sprite([".kkkk.", "kWWWWk", "kWkkWk", "...kWk", "..kWk.", "..kWk.", "......", "..kWk."])
    c.blit(QM, 192, 37)
    # фигурка
    hx, hy = pp[step]
    hx, hy = round(hx / s), round(hy / s) + 2
    for dx in range(-6, 7):
        c.put(hx + dx, hy + 1, "G")
    c.blit(FOX, hx + 1, hy)
    big = c.img.resize((PW * Z, PH * Z), Image.NEAREST).crop((0, 0, 800, 450))
    big.save(OUT / out)


if __name__ == "__main__":
    scene()

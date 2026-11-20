"""Макет экрана «Мои герои»: 8 персонажей, часть закрыта (силуэт + замок + условие)."""
from common import f, render, svg_doc
from heroes import HEROES, hero

# пример условий — только для макета, правила открытия ещё не решены
LOCKS = {"fox": None, "cat": None, "bear": None, "bunny": "серия 7 дней", "penguin": "зона «Снега»",
         "owl": "30 тренировок дня", "dino": "500 монет", "robot": "зона «Город»"}
SELECTED = "fox"


def lock(x, y):
    return (f'<g transform="translate({x} {y})"><path d="M-7 -4 v-5 a7 7 0 0 1 14 0 v5" fill="none" stroke="#f3f5fa" '
            f'stroke-width="3.2"/><rect x="-10" y="-4" width="20" height="15" rx="3.5" fill="#ffc94a" '
            f'stroke="#9a6a0c" stroke-width="1.6"/><circle cx="0" cy="2.5" r="2.4" fill="#9a6a0c"/></g>')


def scene():
    defs = ('<linearGradient id="bg" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#7cc4f5"/>'
            '<stop offset="1" stop-color="#c8ecff"/></linearGradient>'
            '<radialGradient id="ped" cx="0.5" cy="0.35" r="0.7"><stop offset="0" stop-color="#ffffff"/>'
            '<stop offset="1" stop-color="#d9e6f2"/></radialGradient>'
            '<radialGradient id="sel" ><stop offset="0" stop-color="#fff6a8" stop-opacity="1"/>'
            '<stop offset="1" stop-color="#ffe14d" stop-opacity="0"/></radialGradient>'
            '<filter id="sil"><feColorMatrix type="matrix" values="0 0 0 0 0.24  0 0 0 0 0.3  0 0 0 0 0.42  0 0 0 1 0"/></filter>')
    o = '<rect width="800" height="450" fill="url(#bg)"/>'
    for cx, cy, r in ((90, 40, 40), (150, 30, 30), (640, 50, 36), (700, 40, 44)):
        o += f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="#fff" opacity="0.5"/>'
    o += '<rect x="0" y="232" width="800" height="218" fill="#9fd36f" opacity="0.0"/>'
    kinds = list(HEROES)
    for i, kind in enumerate(kinds):
        col, row = i % 4, i // 4
        x, y = 100 + col * 200, 175 + row * 215
        locked = LOCKS[kind]
        card_fill = "#ffffff" if not locked else "#e9eef5"
        o += (f'<rect x="{x - 88}" y="{y - 150}" width="176" height="200" rx="18" fill="{card_fill}" opacity="0.92" '
              f'stroke="{"#ffb800" if kind == SELECTED else "#ffffff"}" stroke-width="{5 if kind == SELECTED else 2}"/>')
        if kind == SELECTED:
            o += f'<ellipse cx="{x}" cy="{y - 10}" rx="60" ry="30" fill="url(#sel)"/>'
        o += f'<ellipse cx="{x}" cy="{y - 4}" rx="44" ry="11" fill="url(#ped)" stroke="#b8c7d8" stroke-width="1.5"/>'
        d, g = hero(kind, x, y - 4, 1.75, uid=f"_{i}")
        defs += d
        if locked:
            o += f'<g filter="url(#sil)" opacity="0.8">{g}</g>' + lock(x, y - 62)
        else:
            o += g
        name = HEROES[kind]["name"]
        o += (f'<text x="{x}" y="{y + 22}" font-family="DejaVu Sans" font-weight="bold" font-size="17" '
              f'fill="{"#24324a" if not locked else "#6b7a90"}" text-anchor="middle">{name}</text>')
        if locked:
            o += (f'<text x="{x}" y="{y + 40}" font-family="DejaVu Sans" font-size="12.5" fill="#6b7a90" '
                  f'text-anchor="middle">{locked}</text>')
        elif kind == SELECTED:
            o += (f'<text x="{x}" y="{y + 40}" font-family="DejaVu Sans" font-weight="bold" font-size="12.5" '
                  f'fill="#c98a00" text-anchor="middle">✓ выбран</text>')
        else:
            o += (f'<text x="{x}" y="{y + 40}" font-family="DejaVu Sans" font-size="12.5" fill="#3f8a34" '
                  f'text-anchor="middle">открыт</text>')
    return svg_doc(o, defs)


def singles():
    for kind in HEROES:
        d, g = hero(kind, 60, 128, 1.65)
        render(svg_doc(g, d, 120, 140), f"hero_{kind}.png", 120, 140, zoom=2)


if __name__ == "__main__":
    render(scene(), "gallery.png")
    singles()

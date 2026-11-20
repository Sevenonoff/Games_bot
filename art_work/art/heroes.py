"""Персонажи в стиле «мягкий объём»: чиби-зверята, ноги в (0, 0), рост ~66 px при k=1.

hero(kind, x, y, k) -> (defs, svg)
"""
from common import f, shade

HEROES = {
    "fox":     dict(name="Лисёнок",   main="#f08a2c", belly="#fff4e6", line="#6b3412", feet="#4a2a18"),
    "cat":     dict(name="Котик",     main="#8f98ab", belly="#f4f4f7", line="#3c4252", feet="#6f7789"),
    "bear":    dict(name="Мишка",     main="#a86b3c", belly="#f0d2a8", line="#4a2c14", feet="#6e4220"),
    "bunny":   dict(name="Зайка",     main="#f5f1ec", belly="#ffffff", line="#6b5a52", feet="#e3d9cf"),
    "penguin": dict(name="Пингвин",   main="#33415f", belly="#ffffff", line="#1b2236", feet="#ffa62b"),
    "owl":     dict(name="Совёнок",   main="#8c6a50", belly="#f2e1c4", line="#3f2c1e", feet="#f0a83a"),
    "dino":    dict(name="Динозаврик", main="#6cc24a", belly="#eef7b0", line="#2d5e1e", feet="#4f9a35"),
    "robot":   dict(name="Робот",     main="#7fb6e6", belly="#d7e3ee", line="#2c3e57", feet="#5b7fa6"),
}

SW = 2.2  # толщина контура


def _grad(gid, base):
    return (f'<radialGradient id="{gid}" cx="0.35" cy="0.3" r="0.8">'
            f'<stop offset="0" stop-color="{shade(base, 1.35)}"/>'
            f'<stop offset="0.55" stop-color="{base}"/>'
            f'<stop offset="1" stop-color="{shade(base, 0.82)}"/></radialGradient>')


def _eyes(line, y=-41, dx=6.5, big=False):
    s = ""
    for sx in (-1, 1):
        x = sx * dx
        if big:
            s += (f'<circle cx="{f(x)}" cy="{y}" r="7.2" fill="#fff" stroke="#f0b54a" stroke-width="2.4"/>'
                  f'<circle cx="{f(x + 0.6)}" cy="{y + 0.6}" r="4" fill="#24170f"/>'
                  f'<circle cx="{f(x + 1.8)}" cy="{y - 1}" r="1.5" fill="#fff"/>')
        else:
            s += (f'<ellipse cx="{f(x)}" cy="{y}" rx="3" ry="3.9" fill="#24170f"/>'
                  f'<circle cx="{f(x + 1)}" cy="{y - 1.5}" r="1.3" fill="#fff"/>')
    return s


def _blush(y=-34.5, dx=12):
    return "".join(f'<ellipse cx="{sx * dx}" cy="{y}" rx="3.6" ry="2.2" fill="#ff7a8a" opacity="0.5"/>'
                   for sx in (-1, 1))


def _mouth(line, y=-32.5):
    return (f'<path d="M-3.2 {y} q1.6 2 3.2 0 q1.6 2 3.2 0" fill="none" stroke="{line}" '
            f'stroke-width="1.4" stroke-linecap="round"/>')


def hero(kind, x, y, k=1.0, uid=""):
    h = HEROES[kind]
    main, belly, line, feet = h["main"], h["belly"], h["line"], h["feet"]
    gid = f"hg_{kind}{uid}"
    defs = _grad(gid, main)
    fill = f'url(#{gid})'
    st = f'stroke="{line}" stroke-width="{SW}" stroke-linejoin="round"'
    back, body, head, face, front = [], [], [], [], []

    # тень под ногами
    shadow = '<ellipse cx="0" cy="0" rx="17" ry="5.5" fill="#000" opacity="0.22"/>'

    # ноги
    if kind == "robot":
        for sx in (-1, 1):
            body.append(f'<rect x="{sx * 7 - 5}" y="-7" width="10" height="7" rx="2.5" fill="{feet}" {st}/>')
    else:
        for sx in (-1, 1):
            body.append(f'<ellipse cx="{sx * 6.5}" cy="-2.6" rx="6" ry="4" fill="{feet}" {st}/>')

    # хвосты — за телом
    if kind == "fox":
        back.append(f'<path d="M7 -9 C 26 -6 36 -24 27 -42 C 23 -31 17 -24 9 -21 Z" fill="{fill}" {st}/>')
        back.append(f'<path d="M27 -42 C 30 -36 30 -31 28 -27 C 25 -31 24 -36 27 -42 Z" fill="#fff" '
                    f'stroke="{line}" stroke-width="1.6" stroke-linejoin="round"/>')
    elif kind == "cat":
        back.append(f'<path d="M9 -8 C 24 -7 22 -26 30 -33" fill="none" stroke="{line}" stroke-width="8.4" '
                    f'stroke-linecap="round"/>')
        back.append(f'<path d="M9 -8 C 24 -7 22 -26 30 -33" fill="none" stroke="{main}" stroke-width="4.6" '
                    f'stroke-linecap="round"/>')
    elif kind == "dino":
        back.append(f'<path d="M-8 -7 C -22 -5 -31 -10 -36 -19 C -27 -15 -19 -17 -10 -20 Z" fill="{fill}" {st}/>')
    elif kind == "bunny":
        back.append(f'<circle cx="11" cy="-9" r="5.5" fill="#fff" {st}/>')

    # тело
    if kind == "robot":
        body.append(f'<rect x="-12.5" y="-29" width="25" height="23" rx="7" fill="{fill}" {st}/>')
        body.append(f'<rect x="-7" y="-23" width="14" height="10" rx="3" fill="{belly}" stroke="{line}" '
                    f'stroke-width="1.4"/>')
        body.append('<path d="M0 -15.2 l-3 -3 a1.8 1.8 0 0 1 3 -2.2 a1.8 1.8 0 0 1 3 2.2 z" fill="#ff5a6e"/>')
    else:
        body.append(f'<ellipse cx="0" cy="-16" rx="12.5" ry="14" fill="{fill}" {st}/>')
        if kind != "owl":
            body.append(f'<ellipse cx="0" cy="-13.5" rx="7.8" ry="9" fill="{belly}"/>')
        else:
            body.append(f'<ellipse cx="0" cy="-14" rx="8.6" ry="10" fill="{belly}"/>')
            for yy in (-19, -13, -7):
                for xx in (-3.5, 3.5):
                    body.append(f'<path d="M{xx - 1.6} {yy} l1.6 1.8 l1.6 -1.8" fill="none" stroke="{shade(main, 0.9)}" '
                                f'stroke-width="1.2" stroke-linecap="round"/>')
        if kind == "dino":
            for cx, cy, r in ((-8, -20, 2), (-9, -11, 1.5), (8, -10, 1.6)):
                body.append(f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{shade(main, 0.8)}"/>')

    # руки / крылья
    if kind in ("penguin", "owl"):
        for sx in (-1, 1):
            body.append(f'<ellipse cx="{sx * 12.5}" cy="-17" rx="4.2" ry="9" fill="{shade(main, 0.92)}" {st} '
                        f'transform="rotate({sx * -18} {sx * 12.5} -17)"/>')
    elif kind == "robot":
        for sx in (-1, 1):
            body.append(f'<rect x="{sx * 15 - 3}" y="-26" width="6" height="13" rx="3" fill="{h["belly"]}" {st}/>')
    else:
        for sx in (-1, 1):
            body.append(f'<ellipse cx="{sx * 11.5}" cy="-19" rx="4" ry="6.5" fill="{main}" {st} '
                        f'transform="rotate({sx * -28} {sx * 11.5} -19)"/>')

    # шарф пингвину
    if kind == "penguin":
        front.append(f'<path d="M4 -24 L9 -11 L3.5 -12 L1 -23 Z" fill="#c9343a" {st}/>')
        front.append(f'<path d="M-12 -27.5 Q0 -21.5 12 -27.5 L11.5 -22.5 Q0 -16.5 -11.5 -22.5 Z" fill="#e5484d" {st}/>')

    # уши — за головой
    if kind == "fox":
        for sx in (-1, 1):
            back.append(f'<path d="M{sx * 17} -46 L{sx * 12} -66 L{sx * 2} -55 Z" fill="{fill}" {st}/>')
            back.append(f'<path d="M{sx * 14} -50 L{sx * 12} -62 L{sx * 6} -55 Z" fill="#4a2a18"/>')
    elif kind == "cat":
        for sx in (-1, 1):
            back.append(f'<path d="M{sx * 17.5} -46 L{sx * 15} -64 L{sx * 4} -56 Z" fill="{main}" {st}/>')
            back.append(f'<path d="M{sx * 15} -50 L{sx * 14.2} -60 L{sx * 8} -55 Z" fill="#ffb3c1"/>')
    elif kind == "bear":
        for sx in (-1, 1):
            back.append(f'<circle cx="{sx * 14}" cy="-54" r="6.8" fill="{main}" {st}/>')
            back.append(f'<circle cx="{sx * 14}" cy="-54" r="3.4" fill="{belly}"/>')
    elif kind == "bunny":
        for sx in (-1, 1):
            back.append(f'<ellipse cx="{sx * 7}" cy="-66" rx="5.4" ry="15" fill="{main}" {st} '
                        f'transform="rotate({sx * 12} {sx * 7} -66)"/>')
            back.append(f'<ellipse cx="{sx * 7}" cy="-65" rx="2.6" ry="10.5" fill="#ffb3c1" '
                        f'transform="rotate({sx * 12} {sx * 7} -66)"/>')
    elif kind == "owl":
        for sx in (-1, 1):
            back.append(f'<path d="M{sx * 16} -48 L{sx * 15} -62 L{sx * 6} -55 Z" fill="{main}" {st}/>')
    elif kind == "dino":
        spike = shade(main, 0.72)
        for xx, yy, r, sz in ((-7, -57, -22, 1), (1, -59.5, 4, 1.15), (9, -56, 30, 0.9), (-24, -15, -70, 0.8),
                              (-31, -18, -75, 0.6)):
            back.append(f'<path d="M-4.5 0 Q-1.5 -9 0 -9.5 Q1.5 -9 4.5 0 Z" fill="{spike}" {st} '
                        f'transform="translate({xx} {yy}) rotate({r}) scale({sz})"/>')
    elif kind == "robot":
        back.append(f'<line x1="0" y1="-58" x2="0" y2="-67" stroke="{line}" stroke-width="2.2"/>')
        back.append(f'<circle cx="0" cy="-68" r="3.4" fill="#ff5a5a" {st}/>')

    # голова
    if kind == "robot":
        head.append(f'<rect x="-17.5" y="-59" width="35" height="31" rx="8" fill="{fill}" {st}/>')
        head.append('<rect x="-12.5" y="-53" width="25" height="19" rx="5" fill="#1f2a3a"/>')
        for sx in (-1, 1):
            head.append(f'<rect x="{sx * 5.5 - 2.4}" y="-48.5" width="4.8" height="6" rx="2.4" fill="#6ff3ff"/>')
        head.append('<path d="M-4 -39.5 q4 3 8 0" fill="none" stroke="#6ff3ff" stroke-width="1.6" '
                    'stroke-linecap="round"/>')
        for sx in (-1, 1):
            head.append(f'<rect x="{sx * 19 - 2.5}" y="-47" width="5" height="9" rx="2" fill="{belly}" {st}/>')
    else:
        rx, ry = (19.5, 17.5) if kind in ("fox", "cat", "bear") else (18.5, 18)
        if kind == "dino":
            rx, ry = 18.5, 17
        head.append(f'<ellipse cx="0" cy="-41" rx="{rx}" ry="{ry}" fill="{fill}" {st}/>')
        if kind == "fox":
            face.append('<path d="M-18.5 -39 Q-10 -31 0 -37 Q10 -31 18.5 -39 Q15 -25 0 -24 Q-15 -25 -18.5 -39 Z" '
                        'fill="#fff4e6"/>')
        elif kind == "bear":
            face.append(f'<ellipse cx="0" cy="-34" rx="8.5" ry="6.3" fill="{belly}"/>')
        elif kind == "penguin":
            face.append('<path d="M0 -46 C -4 -55 -15 -54 -14 -42 C -13 -32 -6 -27 0 -27 C 6 -27 13 -32 14 -42 '
                        'C 15 -54 4 -55 0 -46 Z" fill="#fff"/>')
        elif kind == "cat":
            for dx in (-5, 0, 5):
                face.append(f'<path d="M{dx} -58 l0 5" stroke="{shade(main, 0.75)}" stroke-width="2.2" '
                            f'stroke-linecap="round"/>')
        elif kind == "owl":
            face.append(f'<path d="M-16 -44 Q0 -36 16 -44 Q14 -26 0 -24 Q-14 -26 -16 -44 Z" '
                        f'fill="{shade(main, 1.25)}" opacity="0.6"/>')
        elif kind == "dino":
            face.append(f'<ellipse cx="0" cy="-33" rx="11" ry="6" fill="{shade(main, 1.25)}"/>')
        # блик на голове
        face.append(f'<ellipse cx="-8" cy="-51" rx="5" ry="2.6" fill="#fff" opacity="0.35" '
                    f'transform="rotate(-25 -8 -51)"/>')
        # лицо
        if kind == "owl":
            face.append(_eyes(line, y=-42, dx=7.4, big=True))
            face.append('<path d="M-2.6 -35 L2.6 -35 L0 -30.5 Z" fill="#f0a83a" stroke="#8a5a1a" stroke-width="1"/>')
        elif kind == "penguin":
            face.append(_eyes(line, y=-42, dx=6))
            face.append(f'<path d="M-4 -36 Q0 -38 4 -36 L0 -31.5 Z" fill="#ffa62b" stroke="#a8630f" '
                        f'stroke-width="1"/>')
            face.append(_blush(y=-35.5, dx=10.5))
        else:
            face.append(_eyes(line))
            face.append(_blush())
            if kind == "bunny":
                face.append('<ellipse cx="0" cy="-36" rx="2.2" ry="1.6" fill="#ff8fa3"/>')
                face.append(_mouth(line, -33.8))
                face.append('<rect x="-1.8" y="-32.6" width="3.6" height="3" rx="0.8" fill="#fff" stroke="#6b5a52" '
                            'stroke-width="0.8"/>')
            elif kind == "dino":
                face.append(f'<circle cx="-3" cy="-35" r="0.9" fill="{line}"/>'
                            f'<circle cx="3" cy="-35" r="0.9" fill="{line}"/>')
                face.append(f'<path d="M-5 -31.5 q5 3.4 10 0" fill="none" stroke="{line}" stroke-width="1.4" '
                            f'stroke-linecap="round"/>')
            else:
                face.append(f'<ellipse cx="0" cy="-36.3" rx="2.4" ry="1.7" fill="{line}"/>')
                face.append(_mouth(line))
            if kind == "cat":
                for sx in (-1, 1):
                    for dy in (-1.5, 1.5):
                        face.append(f'<path d="M{sx * 9} {-35 + dy} l{sx * 8} {dy * 1.4}" stroke="{line}" '
                                    f'stroke-width="0.9" stroke-linecap="round" opacity="0.7"/>')

    g = (f'<g transform="translate({f(x)} {f(y)}) scale({k})">{shadow}{"".join(back)}{"".join(body)}'
         f'{"".join(head)}{"".join(face)}{"".join(front)}</g>')
    return defs, g


if __name__ == "__main__":
    from common import render, svg_doc
    defs, body = "", ""
    bg = ('<rect width="800" height="200" fill="#bfe39a"/>')
    for i, kind in enumerate(HEROES):
        d, g = hero(kind, 60 + i * 97, 150, 1.6)
        defs += d
        body += g
    render(svg_doc(bg + body, defs, 800, 200), "heroes_test.png", 800, 200)

"""Глава 2 «Зачарованный лес»: тексты для бота и промпты. Пока готова только локация 9 — первая картинка главы.

Стиль, масштаб и описание тропы — те же, что в главе 1 (иначе глава выпадет из ряда); для леса добавлен
только свет сквозь кроны. Тропа обязательно светлая песочная: по ней бот находит путь (gen/trace.py ищет
светло-бежевые пиксели, V > 0.68 — в тени тропа не найдётся).

python spec.py   — пишет loc9/prompt.txt (полный) и loc9/prompt_short.txt (для моделей с коротким промптом)
"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "chapter1"))
from spec import CLEAN_PROMPT, PATH, SCALE, TAIL  # noqa: E402,F401  — общие с главой 1

CHAPTER = {"id": 2, "title": "Зачарованный лес"}

STYLE = (
    "Art style: stylized hand-painted mobile game map art, soft painterly "
    "brush texture, warm sunny light from the top left, soft shadows, fresh saturated greens, cozy and friendly mood. "
    "Gentle 3/4 top-down camera. The path is warm light sandy beige. "
    "This chapter is a friendly magical forest: golden sunbeams fall through the tree crowns onto a bright sunlit "
    "clearing, deeper emerald greens and soft teal shadows under the trees, a few glowing magical accents, never dark "
    "or scary. The path itself is always in the sun, bright and clearly visible."
)

LOCATIONS = [
    {
        "id": 9, "emoji": "🍄", "name": "Грибная поляна",
        "intro": "Под высокими елями прохладно и тихо. На поляне растут грибы выше путника — а в одном из них "
                 "кто-то живёт.",
        "finish": "Грибы зажгли свои шляпки-фонарики: поляна светится, и тропа видна далеко вперёд.",
        "terrain": "A big sunny clearing inside an enchanted forest; tall fir trees and big old leafy trees grow around "
                   "it and the forest continues beyond every edge of the picture; this is not a floating island and "
                   "there are no cliffs.",
        "route": "The path is a vertical serpentine: it enters at the bottom-left corner, goes up along the left third "
                 "of the map, turns right in a wide bend near the top, comes down through the middle of the map, turns "
                 "right in a wide bend near the bottom, and goes up along the right third to the top-right corner. The "
                 "runs curve gently and are never perfectly straight. The path never touches or crosses itself. The "
                 "mushroom house stands between the first and the second runs, the fairy ring and the stream between "
                 "the second and the third.",
        "scene": "A magical mushroom glade: giant red mushrooms with white spots as tall as trees, one giant mushroom is "
                 "a cozy house with a round door, round windows and a little chimney with smoke, a family of hedgehogs "
                 "picking mushrooms into baskets, a squirrel carrying a big acorn along a branch, a perfect ring of "
                 "small white mushrooms in the grass, a hollow mossy log lying beside the path, a clump of softly "
                 "glowing blue mushrooms in the shade under a fir tree, a little stream with stepping stones where a "
                 "frog sits on a lily pad (the main path does not cross the stream), a mole peeking out of a molehill, "
                 "a wooden signpost with arrows but no writing, butterflies and dandelion seeds floating in the "
                 "sunbeams.",
        "continuity": "In the bottom-left corner, where the path enters, there is still a bit of the previous forest "
                      "edge: a woodpile of cut logs and a lantern on a wooden post.",
        "after": "Show the very same scene at dusk: the caps of the giant mushrooms glow softly like lanterns, the "
                 "glowing blue mushrooms shine brighter, fireflies float over the clearing, warm light in the round "
                 "windows of the mushroom house. Keep everything else exactly the same, same composition and camera.",
    },
]


def scene_prompt(loc):
    """Как в главе 1: без картинок-образцов (с образцом Gemini копирует его планировку или масштаб)."""
    return (
        "Wide 16:9 game level map, one area of a long journey through an enchanted forest.\n\n"
        f"{STYLE}\n\n{SCALE}\n\nLand: {loc['terrain']}\n\nScene: {loc['scene']}\n\n"
        f"Continuity: {loc['continuity']}\n\nRoute of the path: {loc['route']}\n\n{PATH}\n\n{TAIL}"
    )


SHORT = {
    9: (
        "Wide 16:9 hand-painted mobile game level map, gentle 3/4 top-down view, zoomed out like a whole level. "
        "A sunny clearing in a friendly enchanted forest: golden sunbeams through tall fir trees, fresh saturated "
        "greens, soft shadows, cozy mood. One long wide light sandy-beige dirt path of even width enters at the "
        "bottom-left corner, winds up, down and up again in a smooth vertical serpentine across the whole map and "
        "disappears into soft white clouds at the top-right corner; no forks, no loops, nothing stands on the path. "
        "Beside the path: giant red white-spotted mushrooms, one of them a cozy house with a round door and a smoking "
        "chimney, hedgehogs with baskets, a squirrel with an acorn, a fairy ring of small mushrooms, a mossy hollow "
        "log, glowing blue mushrooms in the shade, a stream with stepping stones and a frog, a mole, a signpost "
        "without writing, butterflies. Tiny cute animals, large readable shapes, medium detail. No text, no letters, "
        "no game UI, no coins."
    ),
}


if __name__ == "__main__":
    for loc in LOCATIONS:
        d = HERE / f"loc{loc['id']}"
        d.mkdir(exist_ok=True)
        (d / "prompt.txt").write_text(scene_prompt(loc) + "\n")
        (d / "prompt_short.txt").write_text(SHORT[loc["id"]] + "\n")
        (d / "clean_prompt.txt").write_text(CLEAN_PROMPT + "\n")
        (d / "after_prompt.txt").write_text(loc["after"] + "\n")
        print(d, len(scene_prompt(loc).split()), "слов;", len(SHORT[loc["id"]].split()), "в коротком")

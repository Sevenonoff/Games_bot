"""Глава 1 «Родная долина»: тексты для бота и промпты для Gemini."""

CHAPTER = {"id": 1, "title": "Родная долина"}

STYLE = (
    "Art style: stylized hand-painted mobile game map art, soft painterly "
    "brush texture, warm sunny light from the top left, soft shadows, fresh saturated greens, cozy and friendly mood. "
    "Gentle 3/4 top-down camera. The path is warm light sandy beige."
)

SCALE = (
    "Zoomed-out wide view of a big area with many objects, like a whole level map: the main building takes only "
    "about one eighth of the picture width, trees are small, the path is about as wide as one twentieth of the "
    "picture height, and there is room for many objects and long runs of the path."
)

PATH = (
    "The path: one single long, wide, sandy dirt path with the same even width everywhere. It enters at the bottom-left "
    "corner of the picture and winds across the whole map in several big smooth bends, so that it covers most of the map, "
    "and ends at the top-right corner, where it disappears into soft fluffy white clouds. No forks, no branches, no loops, "
    "no second path. Small footpaths to houses, if any, must be narrow and made of grey stepping stones, clearly different "
    "from the main path. Nothing stands on the main path and nothing covers it: buildings, trees and props stand beside "
    "it, with a strip of grass between them and the path."
)

TAIL = (
    "Tiny cute animal villagers in the same hand-painted style bring the scene to life; they are small. Hidden somewhere "
    "in the scene, small but findable, sits a tiny snail with a tiny backpack. Large readable shapes, medium detail, easy "
    "to read on a small phone screen. No text, no letters, no numbers, no signs with writing, no game UI, no coins, no "
    "markers on the path."
)

LOCATIONS = [
    {
        "id": 1, "name": "Луг у дома",
        "intro": "Здесь всё начинается. Карта в рюкзаке, бабушкины пирожки в дорогу — вперёд!",
        "finish": "Над лугом встала радуга. Облака впереди расступаются…",
        "after": "Show the very same scene a little later: a soft rainbow arcs over the meadow, more wildflowers have "
                 "bloomed. Keep everything else exactly the same, same composition and camera.",
    },
    {
        "id": 2, "name": "Ферма тётушки Бурёнки",
        "intro": "На ферме собирают урожай. Одна тыква выросла такая, что её катят втроём.",
        "finish": "Огромную тыкву погрузили на телегу и украсили лентой — первый приз ярмарки!",
        "terrain": 'Gentle open farmland that continues beyond every edge of the picture (not an island, no cliffs at the edges).',
        "route": 'The path enters at the bottom-left corner, runs to the right along the lower part of the map, makes one big U-turn around the barn standing in the middle of the map, runs back to the left across the middle, and then climbs in a long diagonal to the top-right corner.',
        "scene": "A cozy farm: a big red barn with a hay loft, a vegetable garden with giant orange pumpkins (one pumpkin "
                 "is so huge that three little animals are pushing it), a scarecrow with a crow sitting on its hat, a hen "
                 "leading a line of yellow chicks, a piglet in a mud puddle, a wooden cart loaded with hay.",
        "continuity": "In the bottom-left corner, where the path enters, there are still a few things from the previous "
                      "area: the same kind of wooden fence and a round leafy tree.",
        "after": "Show the very same scene a little later: the giant pumpkin now lies on the wooden cart decorated with a "
                 "big red ribbon, baskets full of vegetables stand by the barn. Keep everything else exactly the same.",
    },
    {
        "id": 3, "name": "Пасека и яблоневый сад",
        "intro": "Пахнет мёдом и яблоками. Пасечник угощает путников.",
        "finish": "На столе под яблоней — чай, мёд в баночках и пирог. Всех зовут к столу.",
        "terrain": 'A sunny orchard on gentle slopes that continue beyond every edge of the picture; this is not a floating island and there are no cliffs at the edges.',
        "route": 'The path is a vertical serpentine: it enters at the bottom-left corner, goes up along the left third of the map, turns right in a wide bend near the top, comes down through the middle of the map, turns right in a wide bend near the bottom, and goes up along the right third to the top-right corner. The runs curve gently and are never perfectly straight. The path never touches or crosses itself. The beehives stand between the first and the second runs, the apple orchard between the second and the third.',
        "scene": "A bee farm and an apple orchard: rows of colorful wooden beehives with little bees, an apple orchard with "
                 "red apples, a tall ladder leaning on the tallest apple tree, baskets full of apples, a swing hanging "
                 "from a branch, a small bear beekeeper in a hat with a veil, a little stream with a wooden footbridge "
                 "where a hedgehog is washing apples (the main path does not cross the stream).",
        "continuity": "In the bottom-left corner, where the path enters, there is still a bit of the previous farm: a few "
                      "pumpkins and a piece of wooden fence.",
        "after": "Show the very same scene a little later: a table under the biggest apple tree with tea, jars of golden "
                 "honey and an apple pie, little animals gathering around. Keep everything else exactly the same.",
    },
    {
        "id": 4, "name": "Деревня на холме",
        "intro": "В деревне все уже знают про старую карту — и каждый советует своё.",
        "finish": "Над площадью развесили флажки: деревня провожает путника.",
        "terrain": 'A rounded green hill that fills the picture, the land continues beyond every edge; this is not a floating island.',
        "route": 'The path climbs the hill in switchbacks: from the bottom-left corner four runs go back and forth across the slope, connected by wide hairpin bends, and the last run reaches the top-right corner. The runs curve gently. The path never touches or crosses itself. The village houses and the square with the well stand between the runs, the square between the two upper runs.',
        "scene": "A small village on a gentle hill with cozy houses with orange and red tiled roofs: a cobblestone square "
                 "with a stone well, a bakery with pretzels in the window and a smoking chimney, a post office with a "
                 "pigeon mail carrier, a blacksmith forge with flying sparks, a cat sleeping on a roof, laundry hanging on "
                 "a line between two houses, a rooster weather vane on a roof.",
        "continuity": "In the bottom-left corner, where the path enters, there are still a couple of apple trees and a "
                      "beehive from the previous orchard.",
        "after": "Show the very same scene a little later: colorful garlands of little flags hang across the square, a "
                 "long table with pies stands by the well. Keep everything else exactly the same.",
    },
    {
        "id": 5, "name": "Летняя ярмарка",
        "intro": "Сегодня ярмарка! Говорят, с колеса обозрения видно край облаков.",
        "finish": "Стемнело, зажглись фонарики, а в небе — салют!",
        "terrain": 'A wide flat meadow that continues beyond every edge of the picture; this is not a floating island and there are no cliffs.',
        "route": 'The path is a wide sideways S with soft curves: from the bottom-left corner it runs to the right along the lower third, curving around the carousel, turns up in a wide bend near the right edge, runs back to the left across the middle, curving around the stage, turns up in a wide bend near the left edge and runs to the top-right corner. The path never touches or crosses itself. The Ferris wheel and the tents stand between the runs.',
        "scene": "A summer fair on a meadow: colorful striped tents, a small Ferris wheel, a carousel with wooden horses, a "
                 "stage with a frog band playing music, a cotton candy stall, a stall with toy prizes, a raccoon juggling "
                 "balls, bunches of balloons, one balloon flying away toward the clouds, strings of colorful flags.",
        "continuity": "In the bottom-left corner, where the path enters, there is still the edge of the previous village: "
                      "a house with an orange tiled roof and a garland of flags.",
        "after": "Show the very same scene in the evening: warm lanterns and string lights are lit everywhere, the Ferris "
                 "wheel glows, colorful fireworks in the darkening sky. Keep the composition exactly the same.",
    },
    {
        "id": 6, "name": "Водяная мельница",
        "intro": "Тропа выходит к реке. Там, где течение быстрое, крутится большое колесо.",
        "finish": "Бобры достроили плотину, а по реке плывёт целая флотилия бумажных корабликов.",
        "terrain": 'A green river valley that continues beyond every edge of the picture; this is not a floating island. A calm blue river flows through the upper-left part of the map, from the left edge to the top edge, with a strip of grass between it and the path; the path never crosses the river.',
        "route": 'The path is a vertical serpentine: from the bottom-left corner it goes up, turns right in a wide bend, comes down, turns right in a wide bend near the bottom, and goes up to the top-right corner. The runs curve gently. The path never touches or crosses itself. The water mill stands on the riverbank close to the first run of the path.',
        "scene": "A green river valley: a calm blue river flows along the right side and the top of the map (the main path "
                 "runs beside the river and never crosses it), a stone water mill with a big wooden water wheel, beavers "
                 "building a little dam, an otter fishing from a wooden pier, a small boat with ducklings, a little mouse "
                 "miller carrying a flour sack, a heron in the reeds, a paper boat floating on the water, weeping willow "
                 "trees.",
        "continuity": "In the bottom-left corner, where the path enters, there is still a bit of the previous fair: a "
                      "striped tent and a couple of balloons.",
        "after": "Show the very same scene a little later: the beaver dam is finished and the beavers celebrate on it, a "
                 "whole fleet of paper boats floats down the river. Keep everything else exactly the same.",
    },
    {
        "id": 7, "name": "Холм ветров",
        "intro": "Здесь всегда ветрено. С вершины уже виден тёмный край леса.",
        "finish": "Ветер подхватил все змеи разом — небо стало разноцветным.",
        "terrain": 'A big grassy hill that rises toward the top of the picture, the land continues beyond every edge; this is not a floating island.',
        "route": 'The path climbs the hill in long switchbacks: from the bottom-left corner four long runs go back and forth across the slope, slightly diagonal, connected by wide hairpin bends, and the last run reaches the top-right corner. The path never touches or crosses itself. The windmills stand on the top of the hill, the observatory and the stone circle between the runs.',
        "scene": "A big windy grassy hill: several tall windmills on the hilltop, colorful kites flying, an old round stone "
                 "observatory with a big brass telescope, a sheep shepherd with a flock of fluffy sheep, an ancient circle "
                 "of standing stones, a picnic blanket with a basket, a kite stuck in a tree, little colorful pinwheels, "
                 "far away near the top edge the dark green edge of a pine forest.",
        "continuity": "In the bottom-left corner, where the path enters, there is still a bit of the previous river: "
                      "the riverbank with reeds and a weeping willow.",
        "after": "Show the very same scene a little later: the sky is full of colorful kites, the windmills spin. Keep "
                 "everything else exactly the same.",
    },
    {
        "id": 8, "name": "Опушка и сторожевая башня",
        "intro": "Последний дом долины. Дальше начинается Зачарованный лес.",
        "finish": "На башне загорелся костёр — его видно со всей долины. Лес ждёт!",
        "terrain": 'A sunlit forest clearing at the end of the valley with a little ravine; the land continues beyond every edge of the picture; this is not a floating island.',
        "route": 'The path is a relaxed sideways S with three long gently curving runs: from the bottom-left corner to the right, a wide bend up, back to the left across the middle, a wide bend up, and to the top-right corner, where it disappears among the first tall fir trees into soft clouds. The path never touches or crosses itself. The watchtower stands between the middle and the upper runs.',
        "scene": "The edge of a forest at the end of the valley, warm late-afternoon light: a tall wooden watchtower with an "
                 "unlit bonfire bowl on top, a forester's log cabin with a woodpile, a small sawmill, a fox forester with "
                 "a lantern, a hare peeking out of a burrow, mushrooms around a stump, a spring with clear water, a small "
                 "wooden bridge over a ravine beside the path, fireflies, and at the top of the picture the first tall fir "
                 "trees of a dense magical forest.",
        "continuity": "In the bottom-left corner, where the path enters, there is still a bit of the previous hill: grass "
                      "with a couple of standing stones and a pinwheel.",
        "after": "Show the very same scene at sunset: a big bonfire is burning brightly on top of the watchtower, its warm "
                 "glow lights the clearing, fireflies everywhere. Keep everything else exactly the same.",
    },
]


def scene_prompt(loc):
    """Без картинок-образцов: с образцом Gemini копирует его планировку или его масштаб."""
    return (
        "Wide 16:9 game level map, one area of a long journey through a cozy valley.\n\n"
        f"{STYLE}\n\n{SCALE}\n\nLand: {loc['terrain']}\n\nScene: {loc['scene']}\n\n"
        f"Continuity: {loc['continuity']}\n\nRoute of the path: {loc['route']}\n\n{PATH}\n\n{TAIL}"
    )


CLEAN_PROMPT = (
    "Edit this image. Remove every tall object that stands on the ground: buildings, towers, windmills, trees, bushes, "
    "tents, carts, fences, signs, stalls, big rocks, characters and animals. Where they stood, paint the same ground they "
    "stood on (grass, cobblestones or sand), and where they were hiding the sandy path, paint the continuation of that "
    "path so the whole path is fully visible. Keep water, the cliffs at the edges, the clouds and flat things like flower "
    "beds as they are. Keep the camera, the composition and the colors exactly the same. Do not add anything."
)

ADD_SNAIL_1 = (
    "Edit this image. Add a tiny snail with a tiny backpack sitting on the grey boulder near the wooden fence on the "
    "left, and a small green frog sitting on a lily pad in the pond. Both are small. Keep everything else exactly the "
    "same: composition, camera, colors and every object in its place."
)

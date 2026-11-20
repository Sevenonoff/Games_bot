"""Кадры пути из локаций, нарисованных нейросетью: все локации и режимы рисуются, монеты убывают,
герой меняется, галерея героев рисуется."""
import io

import pytest
from PIL import Image

from games_core import heroes, journey_art, journey_scene as js, locations
from games_core.motivation import zone_size

LOCS = locations.all_locations()


def size_of(jpg: bytes):
    return Image.open(io.BytesIO(jpg)).size


def test_chapter_one_is_complete():
    assert [l.id for l in LOCS] == list(range(1, 9))
    for loc in LOCS:
        assert loc.name and loc.intro and loc.finish and loc.chapter == 1
        assert (loc.dir / "bg.jpg").exists() and (loc.dir / "after.jpg").exists()
        assert all((loc.dir / l.file).exists() for l in loc.layers)


@pytest.mark.parametrize("zone", range(len(LOCS)))
def test_every_location_renders(zone):
    n = zone_size(zone)
    for mode, step in (("current", n // 2), ("reveal", 0), ("done", n)):
        jpg = journey_art.render_zone(zone, step, n, mode, "fox")
        assert jpg[:2] == b"\xff\xd8" and size_of(jpg) == (js.W, js.H)
        assert len(jpg) < 300_000          # уходит в мессенджер при каждом новом шаге


@pytest.mark.parametrize("zone", range(len(LOCS)))
def test_path_points_stay_in_frame(zone):
    pts = js.points(LOCS[zone], zone_size(zone) + 1)
    assert len(set(pts)) == len(pts)
    assert all(0 <= x <= js.W and 0 <= y <= js.H for x, y in pts)
    # шаги примерно равные: тропа без скачков (на крутом повороте монеты чуть ближе друг к другу)
    gaps = sorted(((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 for (x0, y0), (x1, y1) in zip(pts, pts[1:]))
    median = gaps[len(gaps) // 2]
    assert gaps[-1] < 1.15 * median and gaps[0] > 0.6 * median


def test_step_hero_and_mode_change_picture():
    a = js.render(0, 5, 25, "current", "fox")
    assert js.render.__wrapped__(0, 5, 25, "current", "fox") == a        # без кэша — тот же кадр
    assert js.render(0, 6, 25, "current", "fox") != a                    # монету собрали, герой шагнул
    assert js.render(0, 5, 25, "current", "cat") != a
    assert js.render(0, 0, 25, "reveal", "fox") != js.render(0, 0, 25, "current", "fox")
    assert js.render(0, 25, 25, "done", "fox") != a
    assert js.render(0, 5, 25, "current", "nobody") == a                 # неизвестный герой — Лисёнок


def test_drawn_zones_after_the_chapter():
    png = journey_art.render_zone(len(LOCS), 3, zone_size(len(LOCS)))
    assert png.startswith(b"\x89PNG")


def test_heroes_gallery():
    hs = tuple((h.key, h.name, h.price) for h in heroes.HEROES)
    a = js.render_heroes(hs, frozenset({"fox", "cat", "bear"}), "fox")
    assert size_of(a) == (js.W, js.H)
    assert js.render_heroes(hs, frozenset({"fox", "cat", "bear"}), "cat") != a
    assert js.render_heroes(hs, frozenset({"fox", "cat", "bear", "owl"}), "fox") != a

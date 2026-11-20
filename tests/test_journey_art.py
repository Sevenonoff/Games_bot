"""Картинки пути, нарисованные кодом (зоны дальше нарисованных нейросетью локаций): все зоны и режимы
рисуются, одинаково при повторе, фигурка двигается."""
import io

import pytest
from PIL import Image

from games_core import journey_art as art
from games_core.motivation import ZONES, zone_size


def size_of(png: bytes):
    return Image.open(io.BytesIO(png)).size


@pytest.mark.parametrize("zone", range(len(ZONES) + 1))
def test_every_zone_renders(zone):
    n = zone_size(zone)
    png = art.render_drawn_zone(zone, n // 2, n)
    assert png.startswith(b"\x89PNG") and size_of(png) == (art.W, art.H)
    assert len(png) < 200_000          # уходит в мессенджер при каждом новом шаге


def test_modes_and_determinism():
    current = art.render_drawn_zone(1, 5, 35)
    assert art.render_drawn_zone.__wrapped__(1, 5, 35) == current      # без кэша — тот же результат
    assert art.render_drawn_zone(1, 6, 35) != current                  # шаг сдвинул фигурку
    assert art.render_drawn_zone(1, 35, 35, "done") != current
    assert art.render_drawn_zone(1, 0, 35, "reveal") != art.render_drawn_zone(1, 0, 35)


def test_tiles_spread_along_path_and_avoid_clouds():
    for n in (25, 35, 40):
        pts = art.path_points(n)
        assert len(pts) == n and len(set(pts)) == n
        x0, y0, x1, y1 = art.CLOUD_BOX
        assert all(not (x + art.TILE_R > x0 and y - art.TILE_R < y1) for x, y in pts)


@pytest.mark.parametrize("days", [5, 30, 100])
def test_cards(days):
    png = art.render_card(days)
    assert size_of(png) == (art.W, art.H)
    assert art.card_kind(days) == {5: "fire", 30: "month", 100: "hundred"}[days]

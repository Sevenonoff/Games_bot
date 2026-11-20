"""Локации пути, нарисованные нейросетью: тексты и тропа из art/journey/loc<N>/loc.json.

Только метаданные (без Pillow), чтобы motivation.py мог брать названия зон.
Зона пути с номером z (с 0) — локация z + 1. Дальше нарисованных локаций — старые зоны, нарисованные кодом.
"""
import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional, Tuple

ROOT = Path(__file__).with_name("art") / "journey"

Point = Tuple[float, float]


@dataclass(frozen=True)
class Layer:
    file: str
    x: int
    y: int
    base: int          # y основания предмета: что ниже (ближе к зрителю) — рисуется поверх


@dataclass(frozen=True)
class Location:
    id: int
    chapter: int
    chapter_title: str
    emoji: str
    name: str
    intro: str
    finish: str
    path: Tuple[Point, ...]       # ломаная тропы в долях кадра, от начала к концу
    layers: Tuple[Layer, ...]

    @property
    def title(self) -> str:
        return f"{self.emoji} {self.name}"

    @property
    def dir(self) -> Path:
        return ROOT / f"loc{self.id}"


@lru_cache(maxsize=None)
def all_locations() -> Tuple[Location, ...]:
    out = []
    for f in sorted(ROOT.glob("loc*/loc.json"), key=lambda p: int(p.parent.name[3:])):
        d = json.loads(f.read_text(encoding="utf-8"))
        out.append(Location(
            id=d["id"], chapter=d["chapter"], chapter_title=d["chapter_title"], emoji=d["emoji"], name=d["name"],
            intro=d["intro"], finish=d["finish"], path=tuple((float(x), float(y)) for x, y in d["path"]),
            layers=tuple(Layer(l["file"], int(l["x"]), int(l["y"]), int(l["base"])) for l in d["layers"])))
    return tuple(out)


def of_zone(zone: int) -> Optional[Location]:
    locs = all_locations()
    return locs[zone] if 0 <= zone < len(locs) else None

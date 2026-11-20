"""Герои пути и монеты.

Монета — за каждый шаг пути, сундук в конце локации — ещё motivation.CHEST_COINS. Монеты считаются по
истории (как шаги), потраченные — по покупкам в БД. Лисёнок, Котик и Мишка открыты сразу, остальных
покупают за монеты. Выбранный герой хранится в settings.hero; если он не открыт — идёт Лисёнок.

Payload'ы:
  hr             экран героев
  hr:<герой>     выбрать открытого / спросить о покупке закрытого
  hrb:<герой>    купить
"""
from dataclasses import dataclass
from typing import TYPE_CHECKING, Dict, List, Optional, Tuple

from . import motivation
from .sessions import Player
from .texts import t
from .ui import Button, Reply, Screen, data

if TYPE_CHECKING:
    from .manager import Manager

ACTIONS = ("hr", "hrb")


@dataclass(frozen=True)
class Hero:
    key: str
    emoji: str
    name: str
    price: int

    @property
    def title(self) -> str:
        return f"{self.emoji} {self.name}"


HEROES: Tuple[Hero, ...] = (
    Hero("fox", "🦊", "Лисёнок", 0),
    Hero("cat", "🐱", "Котик", 0),
    Hero("bear", "🐻", "Мишка", 0),
    Hero("bunny", "🐰", "Зайка", 40),
    Hero("penguin", "🐧", "Пингвин", 60),
    Hero("owl", "🦉", "Совёнок", 90),
    Hero("dino", "🦖", "Динозаврик", 120),
    Hero("robot", "🤖", "Робот", 150),
)
BY_KEY: Dict[str, Hero] = {h.key: h for h in HEROES}
DEFAULT = "fox"


def short_note(n: int) -> str:
    """«Не хватает 1 монеты», «… 40 монет»."""
    return t("hero_short", n=n, word="монеты" if n % 10 == 1 and n % 100 != 11 else "монет")


def earned(j: motivation.Journey) -> int:
    return motivation.coins_earned(j.steps)


def owned(mgr: "Manager", uid: int) -> Dict[str, int]:
    """Открытые герои: {ключ: цена покупки}."""
    out = {h.key: 0 for h in HEROES if h.price == 0}
    out.update(mgr.storage.hero_purchases(mgr.platform, uid))
    return out


def balance(mgr: "Manager", uid: int, j: Optional[motivation.Journey] = None) -> int:
    j = j or motivation.journey(mgr.storage, mgr.platform, uid)
    return earned(j) - sum(mgr.storage.hero_purchases(mgr.platform, uid).values())


def current(mgr: "Manager", uid: int) -> str:
    key = mgr.storage.settings(mgr.platform, uid).get("hero") or DEFAULT
    return key if key in owned(mgr, uid) else DEFAULT


def dispatch(mgr: "Manager", player: Player, parts: List[str]) -> Reply:
    uid = player.user_id
    hero = BY_KEY.get(parts[1]) if len(parts) > 1 else None
    if hero is None:
        return Reply(screen(mgr, player))
    have = owned(mgr, uid)
    if parts[0] == "hrb":
        if hero.key in have:
            return Reply(screen(mgr, player))
        left = balance(mgr, uid) - hero.price
        if left < 0:
            return Reply(screen(mgr, player), short_note(-left))
        mgr.storage.buy_hero(mgr.platform, uid, hero.key, hero.price, mgr.clock())
        mgr.storage.update_settings(mgr.platform, uid, hero=hero.key)
        return Reply(screen(mgr, player), t("hero_bought", name=hero.name))
    if hero.key in have:
        if current(mgr, uid) == hero.key:
            return Reply(None, t("hero_already", name=hero.name))
        mgr.storage.update_settings(mgr.platform, uid, hero=hero.key)
        return Reply(screen(mgr, player), t("hero_selected", name=hero.name))
    coins = balance(mgr, uid)
    if coins < hero.price:
        return Reply(None, short_note(hero.price - coins))
    return Reply(Screen(t("hero_buy_ask", title=hero.title, price=hero.price, left=coins - hero.price), [
        [Button(t("btn_hero_buy"), data("hrb", hero.key)), Button(t("btn_back"), "hr")],
        [Button(t("btn_menu"), "menu")],
    ]))


def screen(mgr: "Manager", player: Player) -> Screen:
    from . import journey_scene
    uid = player.user_id
    have, selected, coins = owned(mgr, uid), current(mgr, uid), balance(mgr, uid)
    buttons = []
    for h in HEROES:
        if h.key == selected:
            label = f"✅ {h.title}"
        elif h.key in have:
            label = h.title
        else:
            label = f"🔒 {h.title} · {h.price}"
        buttons.append(Button(label, data("hr", h.key)))
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    rows.append([Button(t("btn_journey"), "jr"), Button(t("btn_menu"), "menu")])
    image = journey_scene.render_heroes(tuple((h.key, h.name, h.price) for h in HEROES), frozenset(have), selected)
    return Screen(t("heroes_text", coins=coins, chest=motivation.CHEST_COINS), rows, image=image)

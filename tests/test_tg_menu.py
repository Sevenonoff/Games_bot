"""Игры ядра в Telegram: callback_data кнопок и лимиты клавиатуры (sea_fight_aiogram/games_menu.py)."""
import pytest

from games_core.ui import Button, Screen
from sea_fight_aiogram import games_menu as tg
from tests.harness import World


def test_core_buttons_get_prefix_and_come_back():
    for core in ("menu", "rec", "rec:memo", "new:tower", "t:abc123:13:6", "q:abc123", "dbg:level:memo:5"):
        assert tg.tg_data(core) == "g:" + core
        assert tg.core_payload(tg.tg_data(core)) == core


def test_sea_buttons_lead_to_native_sea_fight():
    assert tg.tg_data("sea") == "sea_menu"
    assert tg.tg_data("sea_rec") == "leaderboard_show"
    # callback'и морского боя — не ядра
    for native in ("sea_menu", "leaderboard_show", "menu", "fire_1_2", "mpfire_3_4", None):
        assert tg.core_payload(native) is None


def test_limits():
    with pytest.raises(ValueError):
        tg.tg_rows(Screen("x", [[Button("a", "noop")] * 9]))
    with pytest.raises(ValueError):
        tg.tg_rows(Screen("x", [[Button("a", "noop")] * 7] * 15))
    with pytest.raises(ValueError):
        tg.tg_rows(Screen("x", [[Button("a", "x" * 63)]]))


async def test_tg_records_have_no_core_sea_games():
    world = World(platform="tg")
    chat = world.chat()
    try:
        await chat.send("menu")
        await chat.click("Рекорды")
        assert [b.data for b in chat.buttons] == ["rec:memo", "rec:matrix", "rec:tower", "sea_rec", "menu"]
        # рекорды морского боя ядра в TG не открываются — вместо них меню
        await chat.press("rec:sea_full")
        assert chat.text == world.mgr.records_menu().text
    finally:
        await world.close()


async def test_tg_has_no_core_multiplayer():
    """В TG бой с другом свой (sea_fight_aiogram): код приглашения текстом и mp-кнопки ведут в меню."""
    world = World(platform="tg")
    chat = world.chat()
    try:
        await chat.send("mpj:ABC234")
        assert chat.text == world.mgr.menu_screen().text
        await chat.press("mp")
        assert chat.text == world.mgr.menu_screen().text
        assert not world.mgr.mp.games
    finally:
        await world.close()

"""Игры ядра в Telegram: callback_data кнопок и лимиты клавиатуры (sea_fight_aiogram/games_menu.py)."""
import pytest

from games_core.ui import Button, Screen
from sea_fight_aiogram import games_menu as tg


def test_core_buttons_get_prefix_and_come_back():
    for core in ("menu", "sea", "rec", "rec:mp_full", "new:tower", "t:abc123:13:6", "q:abc123",
                 "dbg:level:memo:5", "mpn:3600:reduced:manual", "mpf:ABC234:7:6"):
        assert tg.tg_data(core) == "g:" + core
        assert tg.core_payload(tg.tg_data(core)) == core


def test_old_aiogram_buttons_are_not_core():
    for old in ("menu", "sea_menu", "leaderboard_show", "fire_1_2", "mpfire_3_4", None):
        assert tg.core_payload(old) is None


def test_limits():
    with pytest.raises(ValueError):
        tg.tg_rows(Screen("x", [[Button("a", "noop")] * 9]))
    with pytest.raises(ValueError):
        tg.tg_rows(Screen("x", [[Button("a", "noop")] * 7] * 15))
    with pytest.raises(ValueError):
        tg.tg_rows(Screen("x", [[Button("a", "x" * 63)]]))


def test_player_name_without_at():
    assert tg.format_player_name("@anya", "Аня", 7) == "anya"
    assert tg.format_player_name(None, "Аня", 7) == "Аня"
    assert tg.format_player_name(None, None, 7) == "7"

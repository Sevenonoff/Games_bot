"""Отладочные команды /dbg."""
import pytest

from games_core.texts import t
from games_core.manager import text_payload
from tests.harness import World

ADMIN = 42


@pytest.fixture
async def world():
    w = World(debug_users={ADMIN})
    yield w
    await w.close()
    assert not w.errors, w.errors


def test_text_payload():
    assert text_payload("/dbg level memo 40") == "dbg:level:memo:40"
    assert text_payload("/DBG") == "dbg"
    assert text_payload("привет") == "menu"
    assert text_payload(None) == "menu"


async def test_closed_for_others_but_shows_id(world):
    chat = world.chat(7)
    await chat.send("dbg:level:memo:40")
    assert "Ваш id: <code>7</code>" in chat.text
    assert world.storage.load_progress("max", 7, "memo").level == 1


async def test_menu_and_bad_args(world):
    chat = world.chat()
    await chat.send("dbg")
    assert "Отладка" in chat.text
    for bad in ("dbg:level:sea_full:3", "dbg:level:memo:x", "dbg:level:memo:0",
                "dbg:level:memo:5:3", "dbg:sea_end:huge", "dbg:round:-1"):
        await chat.send(bad)
        assert "Не понял" in chat.text, bad


async def test_sea_end_one_shot_to_win(world):
    chat = world.chat()
    await chat.send("dbg")
    await chat.click("Выстрел до победы")
    await chat.play_right()
    assert "Все корабли потоплены" in chat.text


async def test_memo_end_one_pair_left(world):
    chat = world.chat()
    await chat.send("dbg:memo_end")
    await chat.play_right()
    await chat.play_right()
    assert "Поле собрано" in chat.text


async def test_level_with_streak_then_level_up(world):
    chat = world.chat()
    await chat.send("dbg:level:tower:5:2")
    await chat.click("Играть")
    s = chat.session
    assert s.progress.level == 5
    await world.time.advance(1.0)
    while chat.note is None:
        await chat.play_right()
    assert chat.note == t("note_level_up", level=6)


async def test_level_overrides_abandoned_partia(world):
    chat = world.chat()
    await chat.send()
    await chat.click("Мемо")
    await chat.send("dbg:level:memo:9")    # прерванная партия не должна затереть уровень
    assert world.storage.load_progress("max", ADMIN, "memo").level == 9


async def test_idle_lowers_start_level(world):
    chat = world.chat()
    await chat.send("dbg:level:memo:10")
    await chat.send("dbg:idle:memo:3")
    await chat.click("Играть")
    assert chat.session.progress.level == 7


async def test_short_round_only_for_admin(world):
    admin, other = world.chat(), world.chat(7)
    await admin.send("dbg")
    await admin.click("Партия 5 с")
    for chat in (admin, other):
        await chat.send()
        await chat.click("Матрица")
    await world.time.advance(5.0)
    assert "Партия окончена" in admin.text
    assert "Партия окончена" not in other.text
    await admin.send("dbg:round:0")
    assert ADMIN not in world.mgr.round_overrides


async def test_reset_clears_records(world):
    chat = world.chat()
    await chat.send("dbg:sea_end")
    await chat.play_right()
    assert world.storage.top("max", "sea_reduced")
    await chat.send("dbg")
    await chat.click("Стереть")
    assert world.storage.top("max", "sea_reduced") == []
    assert world.storage.load_progress("max", ADMIN, "sea_reduced").best_score == 0

"""Сценарии «как в мессенджере»: нажатия по подписям кнопок, время виртуальное."""
import pytest

from games_core.texts import t
from tests.harness import World, wait_preview, win_round, wrong_move


@pytest.fixture
async def world():
    w = World()
    yield w
    await w.close()
    assert not w.errors, w.errors


async def test_sea_reduced_win_then_records(world):
    chat = world.chat()
    await chat.send()
    await chat.click("Морской бой")
    await chat.click("Малый")
    while "Партия окончена" not in chat.text:
        await chat.play_right()
    assert "Все корабли потоплены" in chat.text and "Новый рекорд" in chat.text

    await chat.click("Меню")
    await chat.click("Рекорды")
    await chat.click("Морской бой (малый)")
    assert "Тестер" in chat.text and "← вы" in chat.text
    await chat.click("Играть")
    assert chat.session.game == "sea_reduced"


async def test_sea_quit_returns_to_menu(world):
    chat = world.chat()
    await chat.send()
    await chat.click("Морской бой")
    await chat.click("Полный")
    await chat.tap(0, 0)
    await chat.click("Закончить")
    assert "не записан" in chat.text
    await chat.click("Ещё раз")
    assert chat.session.game == "sea_full" and not chat.session.finished


async def test_matrix_minute_passes_on_virtual_time(world):
    chat = world.chat()
    await chat.send()
    await chat.click("Матрица")
    assert t("phase_countdown", n=3) in chat.text and "⏱ 60 с" in chat.text
    await chat.tap(0, 0)
    assert chat.note == t("note_countdown")

    await world.time.advance(2.0)        # «2», «1», показ — правками сообщения
    assert t("phase_preview") in chat.text and world.messenger.pushes == 3
    await chat.tap(0, 0)
    assert chat.note == t("note_preview")

    await world.time.advance(1.0)        # таймер скрыл фигуры
    assert t("phase_matrix") in chat.text and "⏱ 60 с" in chat.text
    assert await win_round(world, chat) == t("note_round_ok")

    await wait_preview(world, chat)      # отсчёт и показ время партии не тратят
    assert "⏱ 60 с" in chat.text
    await world.time.advance(12.0)       # таймер обновляется сам, без нажатий
    assert "⏱ 50 с" in chat.text
    await world.time.advance(17.0)
    await chat.tap(*wrong_move(chat.session))
    assert chat.note == t("note_round_fail") and "⏱ 31 с" in chat.text

    await wait_preview(world, chat)
    await world.time.advance(31.0)       # конец минуты тоже приходит правкой
    assert "Партия окончена" in chat.text and "Раундов пройдено: 1 из 2" in chat.text
    assert world.storage.top("max", "matrix")[0][:2] == (42, "Тестер")


async def test_tower_level_up_after_three_rounds(world):
    chat = world.chat()
    await chat.send()
    await chat.click("Башня")
    assert await win_round(world, chat) == t("note_round_ok")
    assert await win_round(world, chat) == t("note_round_ok")
    assert await win_round(world, chat) == t("note_level_up", level=2)
    assert "уровень 2" in chat.text


async def test_matrix_level_down_after_two_errors(world):
    world.mgr.debug_users = frozenset({42})
    chat = world.chat()
    await chat.send("dbg:level:matrix:3")
    await chat.click("Играть")
    for note in (t("note_round_fail"), t("note_level_down", level=2)):
        await wait_preview(world, chat)
        await chat.tap(*wrong_move(chat.session))
        assert chat.note == note


async def test_text_message_interrupts_partia_and_old_buttons_go_stale(world):
    chat = world.chat()
    await chat.send()
    await chat.click("Мемо")
    old_cell = chat.cell(0, 0).data
    await chat.send()                   # любое сообщение — новое меню, партия прервана
    assert chat.session is None
    await chat.press(old_cell)
    assert chat.note == t("note_stale")
    assert world.storage.load_progress("max", 42, "memo").fail_count == 1


async def test_two_players_do_not_mix(world):
    alice, bob = world.chat(1, "Алиса"), world.chat(2, "Боб")
    for chat in (alice, bob):
        await chat.send()
        await chat.click("Морской бой")
        await chat.click("Малый")
    assert alice.session is not bob.session
    while "Партия окончена" not in alice.text or "Партия окончена" not in bob.text:
        for chat in (alice, bob):
            if "Партия окончена" not in chat.text:
                await chat.play_right()
    assert {name for _, name, _ in world.storage.top("max", "sea_reduced")} == {"Алиса", "Боб"}


async def test_tower_colors_and_inactive_cells(world):
    """Пустые клетки жёлтые всегда, клетки с числами белые; нажатие по пустой — не ошибка."""
    chat = world.chat()
    await chat.send()
    await chat.click("Башня")
    s = chat.session
    empty = next((r, c) for r in range(s.round.rows) for c in range(s.round.cols)
                 if (r, c) not in s.round.cells)
    numbered = next(iter(s.round.cells))

    await world.time.advance(2.0)                     # показ
    assert chat.cell(*empty).text == "🟨"
    assert chat.cell(*numbered).text == str(s.round.cells[numbered])
    await world.time.advance(1.0)                     # ввод
    assert chat.cell(*empty).text == "🟨" and chat.cell(*numbered).text == "⬜"

    await chat.tap(*empty)
    assert chat.note is None and s.progress.fail_count == 0 and s.round.opened == 0
    await chat.play_right()
    first = min(s.round.cells, key=s.round.cells.get)
    assert chat.cell(*first).text == str(s.round.numbers[0])
